from web3 import Web3
from typing import List, Dict, Optional
import logging
import requests

logger = logging.getLogger(__name__)


# Minimal ABI for NewLocalMessage event
PIPE_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "msgId", "type": "uint64"},
            {"indexed": False, "name": "amount", "type": "uint256"},
            {"indexed": False, "name": "relayerFee", "type": "uint256"},
            {"indexed": False, "name": "receiver", "type": "bytes"}
        ],
        "name": "NewLocalMessage",
        "type": "event"
    }
]


class EthereumMonitor:
    """Monitor Ethereum Pipe contract for transactions"""
    
    def __init__(self, rpc_url: str, contract_address: str,
                 etherscan_api_key: Optional[str] = None, 
                 etherscan_api_url: str = "https://api.etherscan.io/v2/api",
                 chain_id: str = "1"):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to Ethereum RPC: {rpc_url}")
        
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.contract = self.w3.eth.contract(address=self.contract_address, abi=PIPE_ABI)
        
        # Etherscan API configuration
        self.etherscan_api_key = etherscan_api_key
        self.etherscan_api_url = etherscan_api_url
        self.chain_id = chain_id
        
        if not etherscan_api_key:
            logger.warning("No Etherscan API key provided - transaction lookup will be disabled")
        
        logger.info(f"Connected to Ethereum at block {self.w3.eth.block_number}")
    
    def get_current_block(self) -> int:
        """Get current block number"""
        return self.w3.eth.block_number
    
    def get_new_local_messages(self, from_block: int, to_block: int = None) -> List[Dict]:
        """Get NewLocalMessage events from Ethereum"""
        if to_block is None:
            to_block = 'latest'
        
        try:
            events = self.contract.events.NewLocalMessage.get_logs(
                from_block=from_block,
                to_block=to_block
            )
            
            messages = []
            for event in events:
                messages.append({
                    'message_id': event['args']['msgId'],
                    'amount': str(event['args']['amount']),
                    'relayer_fee': str(event['args']['relayerFee']),
                    'receiver': event['args']['receiver'].hex(),
                    'block_number': event['blockNumber'],
                    'tx_hash': event['transactionHash'].hex(),
                })
            
            logger.info(f"Found {len(messages)} NewLocalMessage events")
            return messages
            
        except Exception as e:
            logger.error(f"Error fetching events: {e}")
            return []
    
    def find_process_remote_messages_batch(self, from_block: int, msg_ids: List[int]) -> Dict[int, Optional[Dict]]:
        """
        Find processRemoteMessage transactions for multiple message IDs.

        Paginates through Etherscan txlist results (10 000 txs per page) so that
        contracts with many transactions are fully scanned and no message is missed.
        
        Args:
            from_block: Starting block to search from
            msg_ids: List of message IDs to search for
            
        Returns:
            Dict mapping msg_id -> transaction info (or None if not found)
            Transaction info contains: {'status': 'success'/'failed', 'tx_hash': str, 'block_number': int}
        """
        # Initialize result dictionary with None for all msg_ids
        results = {msg_id: None for msg_id in msg_ids}
        
        if not msg_ids:
            return results
        
        if not self.etherscan_api_key:
            logger.debug(f"No Etherscan API key - skipping batch transaction lookup for {len(msg_ids)} messages")
            return results
        
        try:
            # Method ID for processRemoteMessage(uint64,uint256,uint256,address)
            method_id = '0x6efe7df5'
            current_block = self.get_current_block()
            
            logger.debug(f"Batch searching for {len(msg_ids)} message IDs from block {from_block} to {current_block}")
            
            # Base Etherscan API parameters — pagination added in the loop below
            base_params = {
                'chainid': self.chain_id,
                'module': 'account',
                'action': 'txlist',
                'address': self.contract_address,
                'startblock': from_block,
                'endblock': 99999999,
                'sort': 'asc',
                'offset': 10000,  # maximum page size
                'apikey': self.etherscan_api_key
            }

            # Convert msg_ids list to set for faster lookup
            msg_ids_set = set(msg_ids)
            found_count = 0
            page = 1

            while True:
                params = {**base_params, 'page': page}

                # Make API request
                response = requests.get(self.etherscan_api_url, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                
                # Check API response status
                if data.get('status') != '1':
                    error_msg = data.get('message', 'Unknown error')
                    if 'rate limit' in error_msg.lower():
                        logger.warning("Etherscan API rate limit exceeded")
                    elif 'invalid api key' in error_msg.lower():
                        logger.error("Invalid Etherscan API key")
                    elif error_msg == 'No transactions found':
                        # Normal end-of-pagination signal from Etherscan
                        pass
                    else:
                        logger.warning(f"Etherscan API error: {error_msg}")
                    break
                
                transactions = data.get('result', [])
                logger.debug(f"Page {page}: scanning {len(transactions)} transactions for {len(msg_ids)} message IDs")
                
                # Filter and decode transactions
                for tx in transactions:
                    # Filter by method ID
                    tx_method_id = tx.get('methodId', '')
                    if tx_method_id != method_id:
                        continue
                    
                    # Decode input data to extract msgId
                    input_data = tx.get('input', '')
                    if len(input_data) < 74:  # 0x + 8 chars method ID + 64 chars for first param
                        continue
                    
                    # Skip '0x' and method ID (8 chars), get first parameter (64 chars for uint64)
                    # The msgId is the first parameter (uint64) but padded to 64 hex chars (32 bytes)
                    msg_id_hex = input_data[10:74]  # Characters 10-73 (64 chars)
                    
                    try:
                        decoded_msg_id = int(msg_id_hex, 16)
                    except ValueError:
                        logger.debug(f"Failed to decode msgId from tx {tx.get('hash')}")
                        continue
                    
                    # Check if this is one of the messages we're looking for
                    if decoded_msg_id in msg_ids_set:
                        tx_status = tx.get('txreceipt_status', '1')
                        is_error = tx.get('isError', '0')
                        block_number = int(tx.get('blockNumber', 0))
                        tx_hash = tx.get('hash', '')
                        
                        status = 'success' if tx_status == '1' and is_error == '0' else 'failed'
                        
                        # Only count the first time we see this msg_id; subsequent entries
                        # (e.g. a failed relay followed by a successful retry) update the
                        # result in-place so the last tx (highest block, asc order) wins.
                        if results[decoded_msg_id] is None:
                            found_count += 1
                        
                        results[decoded_msg_id] = {
                            'status': status,
                            'tx_hash': tx_hash,
                            'block_number': block_number
                        }
                        logger.debug(f"Found msgId {decoded_msg_id} in tx {tx_hash} at block {block_number} (status: {status})")
                        
                        # Early exit if we found all messages
                        if found_count == len(msg_ids):
                            break

                if found_count == len(msg_ids):
                    break

                # If the page returned fewer results than the page size, we've reached the end
                if len(transactions) < base_params['offset']:
                    break

                page += 1
            
            not_found = len(msg_ids) - found_count
            logger.info(f"Batch lookup: found {found_count}/{len(msg_ids)} messages ({not_found} not found)")
            
            return results
            
        except requests.exceptions.Timeout:
            logger.error("Etherscan API timeout during batch lookup")
            return results
        except requests.exceptions.RequestException as e:
            logger.error(f"Etherscan API request failed during batch lookup: {e}")
            return results
        except Exception as e:
            logger.error(f"Error during batch processRemoteMessage lookup: {e}")
            return results
