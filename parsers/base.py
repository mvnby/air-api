from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseParser(ABC):
    """
    Abstract base class for all product parsers.
    Each parser must implement methods to validate URL support and parse data.
    """

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Check if this parser supports the given URL."""
        pass

    @abstractmethod
    async def parse(self, url: str) -> Dict[str, Any]:
        """
        Parse product data from the URL.
        Returns a dictionary matching the Product model structure.
        """
        pass
