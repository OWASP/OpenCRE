class DocumentFormatException(Exception):
    pass


class InvalidDocumentNameException(DocumentFormatException):
    pass


class InvalidCREIDException(DocumentFormatException):
    def __init__(self, cre):
        self.message = f"CRE ID '{cre.id}' does not fit pattern '\d\d\d-\d\d\d', cre name is  {cre.name}"
        super().__init__(self.message)
