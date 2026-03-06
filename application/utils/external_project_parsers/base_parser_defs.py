from typing import List, Dict, Optional, Sequence, Mapping
from dataclasses import dataclass, field
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
from application.database import db

# abstract class/interface that shows how to import a project that is not cre or its core resources


@dataclass
class ParseResult(object):
    results: Mapping[str, Sequence[defs.Document]] = field(default_factory=dict)
    calculate_gap_analysis: bool = True
    calculate_embeddings: bool = True


class ParserInterface(object):
    # The name of the resource being parsed
    name: str

    def parse(
        self,
        database: db.Node_collection,
        prompt_client: Optional[prompt_client.PromptHandler],
    ) -> ParseResult:
        """
        Parses the resources of a project,
        links the resource of the project to CREs
        this can be done either using glue resources, AI or any other supported method
        then calls cre_main.register_node
        Returns a dict with a key of the resource for importing and a value of list of documents with CRE links, optionally with their embeddings filled in
        """
        raise NotImplementedError
