"""SQLAlchemy models for bridge monitor database"""
import enum
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TransactionStatus(str, enum.Enum):
    """Valid status values for bridge transactions.

    - PENDING:   Transaction is recorded on one chain but not yet completed on the other.
    - COMPLETED: Transaction has been confirmed on both chains.
    - FAILED:    Transaction failed (e.g. reverted or rejected on the destination chain).
    """
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class EthToBeamTransaction(Base):
    """Transaction model for Ethereum → Beam bridge transfers"""
    __tablename__ = "eth_to_beam_transactions"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Core fields
    token: Mapped[str] = mapped_column(String, nullable=False, default="BEAM", index=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=TransactionStatus.PENDING, index=True)
    
    # Ethereum side (source)
    eth_block_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eth_tx_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Transaction details
    receiver: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    amount: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    relayer_fee: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Unique constraint
    __table_args__ = (
        Index('idx_unique_eth2beam', 'token', 'message_id', unique=True),
    )
    
    def __repr__(self) -> str:
        return f"<EthToBeamTransaction(id={self.id}, token={self.token}, msg_id={self.message_id}, status={self.status})>"
    
    def to_dict(self) -> dict:
        """Convert model to dictionary (for compatibility with existing code)"""
        return {
            'id': self.id,
            'token': self.token,
            'direction': 'eth2beam',
            'message_id': self.message_id,
            'status': self.status,
            'eth_block_number': self.eth_block_number,
            'eth_tx_hash': self.eth_tx_hash,
            'receiver': self.receiver,
            'amount': self.amount,
            'relayer_fee': self.relayer_fee,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class BeamToEthTransaction(Base):
    """Transaction model for Beam → Ethereum bridge transfers"""
    __tablename__ = "beam_to_eth_transactions"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Core fields
    token: Mapped[str] = mapped_column(String, nullable=False, default="BEAM", index=True)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=TransactionStatus.PENDING, index=True)
    
    # Beam side (source)
    beam_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Ethereum side (destination)
    eth_block_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eth_tx_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Transaction details
    receiver: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    amount: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    relayer_fee: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Unique constraint
    __table_args__ = (
        Index('idx_unique_beam2eth', 'token', 'message_id', unique=True),
    )
    
    def __repr__(self) -> str:
        return f"<BeamToEthTransaction(id={self.id}, token={self.token}, msg_id={self.message_id}, status={self.status})>"
    
    def to_dict(self) -> dict:
        """Convert model to dictionary (for compatibility with existing code)"""
        return {
            'id': self.id,
            'token': self.token,
            'direction': 'beam2eth',
            'message_id': self.message_id,
            'status': self.status,
            'eth_block_number': self.eth_block_number,
            'eth_tx_hash': self.eth_tx_hash,
            'beam_height': self.beam_height,
            'receiver': self.receiver,
            'amount': self.amount,
            'relayer_fee': self.relayer_fee,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
