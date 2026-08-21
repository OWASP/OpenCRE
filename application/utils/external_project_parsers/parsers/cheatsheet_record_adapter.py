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

    return Section(
        artifact_id=f"art:{record.source}:{record.source_id}",
        chunk_id=f"chk:{record.source}:{record.source_id}",
        text=text,
        title_hint=record.title,
        language=_DEFAULT_LANGUAGE,
        source=source,
        locator=locator,
    )
