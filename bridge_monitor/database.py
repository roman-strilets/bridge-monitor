"""Database interface using SQLAlchemy ORM"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Type
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, Session
from .models import Base, EthToBeamTransaction, BeamToEthTransaction

logger = logging.getLogger(__name__)


class Database:
    """SQLAlchemy-based database for transaction tracking with direction-specific models"""
    
    def __init__(self, db_path: str = "bridge_monitor.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema using SQLAlchemy"""
        Base.metadata.create_all(self.engine)
        logger.info(f"Database initialized at {self.db_path}")
    
    def _get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def _get_model_for_direction(self, direction: str) -> Type:
        """Get the appropriate model class based on direction"""
        if direction == 'eth2beam':
            return EthToBeamTransaction
        elif direction == 'beam2eth':
            return BeamToEthTransaction
        else:
            raise ValueError(f"Invalid direction: {direction}. Must be 'eth2beam' or 'beam2eth'")
    
    def upsert_transaction(self, token: str, direction: str, message_id: int, **fields):
        """Insert or update transaction record"""
        fields['updated_at'] = datetime.now(timezone.utc)
        
        # Get the appropriate model for this direction
        Model = self._get_model_for_direction(direction)
        
        with self._get_session() as session:
            # Check if exists
            existing = session.execute(
                select(Model).where(
                    Model.token == token,
                    Model.message_id == message_id
                )
            ).scalar_one_or_none()
            
            if existing:
                # Update existing transaction
                for key, value in fields.items():
                    setattr(existing, key, value)
                logger.debug(f"Updated {direction} transaction: {token} msg_id={message_id}")
            else:
                # Create new transaction
                fields['token'] = token
                fields['message_id'] = message_id
                fields['created_at'] = fields['updated_at']
                
                new_transaction = Model(**fields)
                session.add(new_transaction)
                logger.debug(f"Created {direction} transaction: {token} msg_id={message_id}")
            
            session.commit()
    
    def get_transaction(self, token: str, direction: str, message_id: int) -> Optional[Dict]:
        """Get transaction by token, direction and message_id"""
        Model = self._get_model_for_direction(direction)
        
        with self._get_session() as session:
            transaction = session.execute(
                select(Model).where(
                    Model.token == token,
                    Model.message_id == message_id
                )
            ).scalar_one_or_none()
            
            return transaction.to_dict() if transaction else None
    
    def get_all_transactions(self, token: str = None, direction: str = None, status: str = None) -> List[Dict]:
        """Get all transactions, optionally filtered by token, direction, and/or status"""
        with self._get_session() as session:
            results = []
            
            # Determine which models to query
            if direction == 'eth2beam':
                models = [EthToBeamTransaction]
            elif direction == 'beam2eth':
                models = [BeamToEthTransaction]
            else:
                # Query both tables
                models = [EthToBeamTransaction, BeamToEthTransaction]
            
            for Model in models:
                stmt = select(Model)
                
                if token:
                    stmt = stmt.where(Model.token == token)
                
                if status:
                    stmt = stmt.where(Model.status == status)
                
                stmt = stmt.order_by(Model.message_id)
                
                transactions = session.execute(stmt).scalars().all()
                results.extend([tx.to_dict() for tx in transactions])
            
            # Sort combined results
            if not direction:
                # Sort by direction then message_id
                results.sort(key=lambda x: (x['token'], x['direction'], x['message_id']))
            
            return results
    
    def get_stats(self, token: str = None) -> Dict:
        """Get transaction statistics, optionally filtered by token"""
        stats = {}
        
        with self._get_session() as session:
            # Stats for eth2beam transactions
            stmt = select(
                EthToBeamTransaction.status,
                func.count(EthToBeamTransaction.id).label('count')
            )
            if token:
                stmt = stmt.where(EthToBeamTransaction.token == token)
            stmt = stmt.group_by(EthToBeamTransaction.status)
            
            result = session.execute(stmt).all()
            stats['eth2beam'] = {row.status: row.count for row in result}
            
            # Get total for eth2beam
            total_stmt = select(func.count(EthToBeamTransaction.id))
            if token:
                total_stmt = total_stmt.where(EthToBeamTransaction.token == token)
            total = session.execute(total_stmt).scalar()
            stats['eth2beam']['total'] = total if total else 0
            
            # Stats for beam2eth transactions
            stmt = select(
                BeamToEthTransaction.status,
                func.count(BeamToEthTransaction.id).label('count')
            )
            if token:
                stmt = stmt.where(BeamToEthTransaction.token == token)
            stmt = stmt.group_by(BeamToEthTransaction.status)
            
            result = session.execute(stmt).all()
            stats['beam2eth'] = {row.status: row.count for row in result}
            
            # Get total for beam2eth
            total_stmt = select(func.count(BeamToEthTransaction.id))
            if token:
                total_stmt = total_stmt.where(BeamToEthTransaction.token == token)
            total = session.execute(total_stmt).scalar()
            stats['beam2eth']['total'] = total if total else 0
        
        return stats
    
    def get_max_eth_block_number(self, token: str, direction: str) -> Optional[int]:
        """Get the maximum eth_block_number for a given token and direction
        
        Args:
            token: Token name to filter by
            direction: 'eth2beam' or 'beam2eth'
            
        Returns:
            Maximum eth_block_number or None if no transactions exist
        """
        Model = self._get_model_for_direction(direction)
        
        with self._get_session() as session:
            stmt = select(func.max(Model.eth_block_number)).where(
                Model.token == token,
                Model.eth_block_number.isnot(None)
            )
            max_block = session.execute(stmt).scalar()
            
            return max_block

    def close(self):
        """Close database connection"""
        self.engine.dispose()
        logger.debug("Database connection closed")
