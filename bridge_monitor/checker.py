import logging
import time
from typing import Dict
from .database import Database
from .ethereum_monitor import EthereumMonitor
from .beam_monitor import BeamMonitor

logger = logging.getLogger(__name__)


class TransactionChecker:
    """Main transaction checker for bridge monitoring"""
    
    def __init__(self, config: Dict, db: Database, token: str = None):
        self.config = config
        self.db = db
        self.token_filter = token
        
        # Get common settings
        self.common_config = config['common']
        
        # Determine which tokens to check
        if token:
            if token not in config['tokens']:
                raise ValueError(f"Token '{token}' not found in configuration")
            self.tokens_to_check = {token: config['tokens'][token]}
        else:
            self.tokens_to_check = config['tokens']
    
    def _create_monitors(self, token_name: str, token_config: Dict):
        """Create Ethereum and Beam monitors for a specific token"""
        eth_monitor = EthereumMonitor(
            rpc_url=self.common_config['ethereum']['rpc_url'],
            contract_address=token_config['ethereum']['pipe_contract_address'],
            etherscan_api_key=self.common_config['ethereum'].get('etherscan_api_key'),
            etherscan_api_url=self.common_config['ethereum'].get('etherscan_api_url', 'https://api.etherscan.io/v2/api'),
            chain_id=self.common_config['ethereum'].get('chain_id', '1')
        )
        
        beam_monitor = BeamMonitor(
            wallet_api_url=self.common_config['beam']['wallet_api_url'],
            contract_id=token_config['beam']['pipe_contract_id'],
            wasm_path=token_config['beam']['pipe_wasm_path']
        )
        
        return eth_monitor, beam_monitor
    
    def check_eth2beam_transactions(self, token_name: str, token_config: Dict, eth_monitor: EthereumMonitor):
        """Check Ethereum → Beam transactions for a specific token"""
        logger.info(f"Checking {token_name} Ethereum → Beam transactions...")
        
        # Get starting block from database or fall back to config
        max_block = self.db.get_max_eth_block_number(token_name, 'eth2beam')
        if max_block is not None:
            start_block = max_block + 1
            logger.debug(f"{token_name} ETH→Beam: Resuming from block {start_block} (DB max + 1)")
        else:
            start_block = token_config['ethereum'].get('start_block', 0)
            logger.debug(f"{token_name} ETH→Beam: Starting from configured block {start_block}")
        
        # Get Ethereum events
        messages = eth_monitor.get_new_local_messages(from_block=start_block)
        
        for msg in messages:
            msg_id = msg['message_id']
            block_num = msg['block_number']
            
            status = 'completed'
            
            # Update database
            self.db.upsert_transaction(
                token=token_name,
                direction='eth2beam',
                message_id=msg_id,
                eth_block_number=block_num,
                eth_tx_hash=msg['tx_hash'],
                amount=msg['amount'],
                relayer_fee=msg['relayer_fee'],
                receiver=msg['receiver'],
                status=status
            )
            
            logger.debug(f"{token_name} ETH→Beam msg {msg_id}: {status}")
        
        logger.info(f"Processed {len(messages)} {token_name} ETH→Beam messages")
    
    def check_beam2eth_transactions(self, token_name: str, token_config: Dict, 
                                     beam_monitor: BeamMonitor, eth_monitor: EthereumMonitor):
        """Check Beam → Ethereum transactions for a specific token"""
        logger.info(f"Checking {token_name} Beam → Ethereum transactions...")
        
        # Get all local messages from Beam
        messages = beam_monitor.get_all_local_messages()
        
        # Pre-load existing transaction statuses to skip already-terminal transactions
        existing_statuses = {
            tx['message_id']: tx['status']
            for tx in self.db.get_all_transactions(token=token_name, direction='beam2eth')
        }

        # First pass: collect Beam messages that need Ethereum lookup
        confirmed_msg_ids = []
        
        for msg in messages:
            msg_id = msg['message_id']
            height = msg['height']

            # Skip already-terminal transactions
            if existing_statuses.get(msg_id) in ('completed', 'failed'):
                continue
            
            confirmed_msg_ids.append(msg_id)
        
        # Batch lookup Ethereum transactions for all messages
        eth_txs_by_msg_id = {}
        if confirmed_msg_ids:
            # Always start from the configured deployment block — this is the correct
            # lower bound for any ETH transaction related to this contract.
            # Using a DB-derived block (min or max of already-found transactions) would
            # skip ETH relay transactions that were mined before the first recorded DB
            # entry, which is exactly why some transactions stay "pending" forever.
            # Etherscan's txlist is filtered by contract address so this is cheap even
            # from block 0; the pagination loop handles large ranges safely.
            eth_start_block = token_config['ethereum'].get('start_block', 0)
            
            logger.debug(f"Batch looking up {len(confirmed_msg_ids)} confirmed messages from block {eth_start_block}")
            
            # Single API call for all confirmed messages
            eth_txs_by_msg_id = eth_monitor.find_process_remote_messages_batch(
                from_block=eth_start_block,
                msg_ids=confirmed_msg_ids
            )
        
        # Second pass: process all messages with cached Ethereum lookup results
        for msg in messages:
            msg_id = msg['message_id']
            height = msg['height']

            # Skip already-terminal transactions
            if existing_statuses.get(msg_id) in ('completed', 'failed'):
                continue
            
            # Determine status
            status = 'pending'
            
            # Check Ethereum side
            eth_tx = eth_txs_by_msg_id.get(msg_id)
            
            if eth_tx and eth_tx['status'] == 'success':
                status = 'completed'
            elif eth_tx and eth_tx['status'] == 'failed':
                status = 'failed'
            
            # Update database
            update_fields = {
                'beam_height': height,
                'amount': msg['amount'],
                'relayer_fee': msg['relayer_fee'],
                'receiver': msg['receiver'],
                'status': status
            }
            
            if eth_tx:
                update_fields.update({
                    'eth_tx_hash': eth_tx['tx_hash'],
                    'eth_block_number': eth_tx['block_number']
                })
            
            self.db.upsert_transaction(token_name, 'beam2eth', msg_id, **update_fields)
            
            logger.debug(f"{token_name} Beam→ETH msg {msg_id}: {status}")
        
        logger.info(f"Processed {len(messages)} {token_name} Beam→ETH messages")
    
    def check_all(self):
        """Check all transactions in both directions for all configured tokens"""
        for token_name, token_config in self.tokens_to_check.items():
            logger.info(f"Processing token: {token_name}")
            
            try:
                # Create monitors for this token
                eth_monitor, beam_monitor = self._create_monitors(token_name, token_config)
                
                # Check both directions
                try:
                    self.check_eth2beam_transactions(token_name, token_config, eth_monitor)
                except Exception as e:
                    logger.error(f"Error checking {token_name} ETH→Beam: {e}")
                
                try:
                    self.check_beam2eth_transactions(token_name, token_config, beam_monitor, eth_monitor)
                except Exception as e:
                    logger.error(f"Error checking {token_name} Beam→ETH: {e}")
                    
            except Exception as e:
                logger.error(f"Error processing token {token_name}: {e}")
    
    def get_report(self) -> Dict:
        """Generate status report"""
        # Get stats for all tokens or specific token
        if self.token_filter:
            stats = self.db.get_stats(token=self.token_filter)
            tokens_data = {self.token_filter: stats}
        else:
            tokens_data = {}
            for token_name in self.config['tokens'].keys():
                tokens_data[token_name] = self.db.get_stats(token=token_name)
        
        # Get failed transactions
        failed_txs = []
        for tx in self.db.get_all_transactions(token=self.token_filter):
            if tx['status'] == 'failed':
                failed_txs.append({
                    'token': tx['token'],
                    'direction': tx['direction'],
                    'message_id': tx['message_id'],
                    'status': tx['status'],
                    'eth_tx_hash': tx['eth_tx_hash']
                })
        
        # Get blockchain heights (use first token's monitor)
        first_token = list(self.tokens_to_check.keys())[0]
        first_config = self.tokens_to_check[first_token]
        eth_monitor, beam_monitor = self._create_monitors(first_token, first_config)
        
        return {
            'timestamp': time.time(),
            'tokens': tokens_data,
            'stuck_transactions': failed_txs,
            'eth_block': eth_monitor.get_current_block(),
            'beam_height': beam_monitor.get_current_height()
        }
