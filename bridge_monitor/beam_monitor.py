import requests
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class BeamMonitor:
    """Monitor Beam Pipe contract via Wallet API"""
    
    def __init__(self, wallet_api_url: str, contract_id: str, wasm_path: str):
        self.wallet_api_url = wallet_api_url
        self.contract_id = contract_id
        self.wasm_path = wasm_path
        self._request_id = 0
        
        # Test connection
        try:
            status = self.get_wallet_status()
            logger.info(f"Connected to Beam at height {status['current_height']}")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Beam Wallet API: {e}")
    
    def _make_request(self, method: str, params: dict) -> dict:
        """Make JSON-RPC request to Beam Wallet API"""
        self._request_id += 1
        
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }
        
        try:
            response = requests.post(self.wallet_api_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                raise Exception(f"Beam API error: {data['error']}")
            
            return data.get('result', {})
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Beam API request failed: {e}")
            raise
    
    def get_wallet_status(self) -> dict:
        """Get current wallet status"""
        result = self._make_request('wallet_status', {})
        return result
    
    def get_current_height(self) -> int:
        """Get current blockchain height"""
        status = self.get_wallet_status()
        return status.get('current_height', 0)
    
    def get_local_message_count(self) -> int:
        """Get total count of local messages (Beam → Ethereum)"""
        try:
            result = self._make_request('invoke_contract', {
                'contract_file': self.wasm_path,
                'args': f'action=local_msg_count,cid={self.contract_id}'
            })
            
            output = json.loads(result.get('output', '{}'))
            return output.get('count', 0)
            
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0
    
    def get_local_message(self, msg_id: int) -> Optional[Dict]:
        """Get details of a specific local message"""
        try:
            result = self._make_request('invoke_contract', {
                'contract_file': self.wasm_path,
                'args': f'role=manager,action=local_msg,cid={self.contract_id},msgId={msg_id}'
            })
            
            output = json.loads(result.get('output', '{}'))
            
            if not output:
                return None
            
            return {
                'message_id': msg_id,
                'receiver': output.get('receiver', ''),
                'amount': str(output.get('amount', 0)),
                'relayer_fee': str(output.get('relayerFee', 0)),
                'height': output.get('height', 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting message {msg_id}: {e}")
            return None
    
    def get_all_local_messages(self) -> list:
        """Get all local messages"""
        count = self.get_local_message_count()
        messages = []
        
        logger.info(f"Fetching {count} local messages from Beam")
        
        # Message IDs start from 1
        for msg_id in range(1, count + 1):
            msg = self.get_local_message(msg_id)
            if msg:
                messages.append(msg)
        
        return messages
    
