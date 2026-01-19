from sqlalchemy.ext.asyncio import AsyncSession
from services.documents.factory import DocumentFactory
from services.documents.base import TEMPLATES # Re-export for compatibility

class DocumentService:
    @staticmethod
    async def create_document(session: AsyncSession, order_id: int, doc_type: str = "contract") -> str:
        """
        Generates a document based on the type.
        Now uses the Strategy pattern via DocumentFactory.
        """
        try:
            strategy = DocumentFactory.get_strategy(doc_type, session, order_id)
            return await strategy.generate(doc_type)
        except Exception as e:
            return f"Error creating document: {str(e)}"
    
    @staticmethod
    def _amount_in_words(amount: float) -> str:
        """
        Deprecated: Logic moved to BaseDocumentStrategy.
        Kept for potential legacy calls.
        """
        from services.documents.base import BaseDocumentStrategy
        return BaseDocumentStrategy(None, 0)._amount_in_words(amount)