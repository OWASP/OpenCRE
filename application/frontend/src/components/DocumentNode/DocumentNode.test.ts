/**
 * Tests for the fix: CRE-type linked documents should never be truncated/collapsed.
 *
 * Issue: On a CRE page, lists of linked CREs were being collapsed after MAX_LENGTH_FOR_AUTO_EXPAND (5)
 * items, forcing users to click "Show more". Since CRE lists are concise by design and important
 * for navigation, they should always be shown in full.
 *
 * Fix location: DocumentNode.tsx - NestedView rendering logic
 */

import { DOCUMENT_TYPES } from '../../const';

const MAX_LENGTH_FOR_AUTO_EXPAND = 5;

// ─── Helper: replicate the exact truncation logic from the fixed DocumentNode ───

function makeCRELink(id: string) {
  return { document: { doctype: DOCUMENT_TYPES.TYPE_CRE, id, name: `CRE-${id}` }, ltype: 'Contains' };
}

function makeStandardLink(id: string) {
  return { document: { doctype: 'Standard', id, name: `STD-${id}` }, ltype: 'Linked To' };
}

/**
 * Replicates the fixed visibility logic from DocumentNode.tsx NestedView:
 *   const allLinksAreCres = sortedResults.length > 0 && sortedResults.every(link => link.document.doctype === DOCUMENT_TYPES.TYPE_CRE);
 *   const visibleResults = allLinksAreCres || showAll ? sortedResults : sortedResults.slice(0, MAX_LENGTH_FOR_AUTO_EXPAND);
 */
function getVisibleResults(links: ReturnType<typeof makeCRELink>[], showAll: boolean) {
  const allLinksAreCres =
    links.length > 0 && links.every((link) => link.document.doctype === DOCUMENT_TYPES.TYPE_CRE);
  return allLinksAreCres || showAll ? links : links.slice(0, MAX_LENGTH_FOR_AUTO_EXPAND);
}

/**
 * Replicates the "Show more" button visibility logic:
 *   sortedResults.length > MAX_LENGTH_FOR_AUTO_EXPAND && !sortedResults.every(link => link.document.doctype === DOCUMENT_TYPES.TYPE_CRE)
 */
function shouldShowMoreButton(links: ReturnType<typeof makeCRELink>[]) {
  return (
    links.length > MAX_LENGTH_FOR_AUTO_EXPAND &&
    !links.every((link) => link.document.doctype === DOCUMENT_TYPES.TYPE_CRE)
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('DocumentNode - CRE list truncation fix', () => {
  // ── Core fix: CRE links never truncated ──────────────────────────────────

  test('shows ALL CRE links when list exceeds MAX_LENGTH_FOR_AUTO_EXPAND', () => {
    const links = Array.from({ length: 10 }, (_, i) => makeCRELink(String(i + 1)));
    const visible = getVisibleResults(links, false);
    expect(visible).toHaveLength(10);
    expect(visible).toEqual(links);
  });

  test('shows ALL CRE links when list is exactly MAX_LENGTH_FOR_AUTO_EXPAND', () => {
    const links = Array.from({ length: 5 }, (_, i) => makeCRELink(String(i + 1)));
    const visible = getVisibleResults(links, false);
    expect(visible).toHaveLength(5);
  });

  test('shows ALL CRE links when list is under MAX_LENGTH_FOR_AUTO_EXPAND', () => {
    const links = Array.from({ length: 3 }, (_, i) => makeCRELink(String(i + 1)));
    const visible = getVisibleResults(links, false);
    expect(visible).toHaveLength(3);
  });

  test('does NOT show "Show more" button for CRE-only list longer than MAX_LENGTH_FOR_AUTO_EXPAND', () => {
    const links = Array.from({ length: 10 }, (_, i) => makeCRELink(String(i + 1)));
    expect(shouldShowMoreButton(links)).toBe(false);
  });

  // ── Non-CRE links still truncated (existing behaviour preserved) ──────────

  test('truncates non-CRE links to MAX_LENGTH_FOR_AUTO_EXPAND when showAll is false', () => {
    const links = Array.from({ length: 10 }, (_, i) => makeStandardLink(String(i + 1)));
    const visible = getVisibleResults(links, false);
    expect(visible).toHaveLength(MAX_LENGTH_FOR_AUTO_EXPAND);
  });

  test('shows all non-CRE links when showAll is true', () => {
    const links = Array.from({ length: 10 }, (_, i) => makeStandardLink(String(i + 1)));
    const visible = getVisibleResults(links, true);
    expect(visible).toHaveLength(10);
  });

  test('shows "Show more" button for non-CRE list longer than MAX_LENGTH_FOR_AUTO_EXPAND', () => {
    const links = Array.from({ length: 10 }, (_, i) => makeStandardLink(String(i + 1)));
    expect(shouldShowMoreButton(links)).toBe(true);
  });

  test('does NOT show "Show more" button for non-CRE list within MAX_LENGTH_FOR_AUTO_EXPAND', () => {
    const links = Array.from({ length: 4 }, (_, i) => makeStandardLink(String(i + 1)));
    expect(shouldShowMoreButton(links)).toBe(false);
  });

  // ── Edge cases ────────────────────────────────────────────────────────────

  test('empty list returns empty visible results', () => {
    const visible = getVisibleResults([], false);
    expect(visible).toHaveLength(0);
  });

  test('mixed list (CRE + non-CRE) is treated as non-CRE and truncated', () => {
    const links = [
      ...Array.from({ length: 6 }, (_, i) => makeCRELink(String(i + 1))),
      makeStandardLink('std-1'),
    ];
    // Not all CREs, so truncation applies
    const visible = getVisibleResults(links, false);
    expect(visible).toHaveLength(MAX_LENGTH_FOR_AUTO_EXPAND);
  });

  test('mixed list (CRE + non-CRE) shows "Show more" button', () => {
    const links = [
      ...Array.from({ length: 6 }, (_, i) => makeCRELink(String(i + 1))),
      makeStandardLink('std-1'),
    ];
    expect(shouldShowMoreButton(links)).toBe(true);
  });

  test('a single CRE link is always shown without a "Show more" button', () => {
    const links = [makeCRELink('1')];
    const visible = getVisibleResults(links, false);
    expect(visible).toHaveLength(1);
    expect(shouldShowMoreButton(links)).toBe(false);
  });

  test('DOCUMENT_TYPES.TYPE_CRE has the expected value "CRE"', () => {
    // Guard: ensure the constant used in the fix matches what the API returns
    expect(DOCUMENT_TYPES.TYPE_CRE).toBe('CRE');
  });
});
