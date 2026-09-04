from pydantic import ValidationError
from application.utils.librarian.section_validator import _DEFAULT_LANGUAGE
from application.defs.cheatsheet_defs import CheatsheetRecord
from application.utils.librarian.schemas import (
    Locator,
    LocatorKind,
    SourceRef,
    SourceType,
)
from application.utils.librarian.section_validator import (
    Section,
    SectionValidationError,
)


class MalformedCheatsheetRecordError(SectionValidationError):
    pass


def section_from_cheatsheet_record(
    record: CheatsheetRecord,
) -> Section:
    text = "\n".join([record.summary, *record.headings])

    try:
        source = SourceRef(
            type=SourceType.url,
            url=record.hyperlink,
            committed_at=record.metadata.get("committed_at"),
        )

        locator = Locator(
            kind=LocatorKind.url,
            id=record.source_id,
            url=record.hyperlink,
        )
    except ValidationError as exc:
        raise MalformedCheatsheetRecordError(str(exc)) from exc

    # Match Module A identity shape: artifact is the document; chunk_id nests
    # under it. One CheatsheetRecord == one chunk, so index is always 0.
    artifact_id = f"art:{record.source}:{record.source_id}"
    return Section(
        artifact_id=artifact_id,
        chunk_id=f"chk:{artifact_id}:0",
        text=text,
        title_hint=record.title,
        language=_DEFAULT_LANGUAGE,
        source=source,
        locator=locator,
    )
