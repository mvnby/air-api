class ManagedDocumentError(ValueError):
    pass


class ManagedDocumentNotFoundError(ManagedDocumentError):
    pass


class ManagedDocumentConflictError(ManagedDocumentError):
    pass


class ManagedDocumentGenerationError(ManagedDocumentError):
    pass
