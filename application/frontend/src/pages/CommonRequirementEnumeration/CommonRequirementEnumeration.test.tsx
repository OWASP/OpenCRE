import { render, waitFor } from '@testing-library/react';
import axios from 'axios';
import React from 'react';
import { MemoryRouter, Route } from 'react-router-dom';

import { CommonRequirementEnumeration } from './CommonRequirementEnumeration';

jest.mock('axios');
jest.mock('../../hooks/useEnvironment', () => ({
  useEnvironment: () => ({ name: 'test', apiUrl: '/rest/v1' }),
}));
// applyFilters constructs `new Document()` at module load (Document is an interface).
jest.mock('../../hooks/applyFilters', () => ({
  applyFilters: (doc: unknown) => doc,
  filterContext: {},
}));
jest.mock('../../components/DocumentNode', () => ({
  DocumentNode: () => null,
}));
// utils/index.ts opens IndexedDB at import time; jsdom has no indexedDB.
jest.mock('../../utils', () => ({
  groupLinksByType: () => ({}),
  scrollMountToTop: () => undefined,
}));
jest.mock('../../utils/document', () => ({
  getDocumentDisplayName: (doc: { name?: string }) => doc?.name || '',
  getDocumentTypeText: (type: string) => type,
  orderLinksByType: (links: unknown) => links,
}));

const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('CommonRequirementEnumeration', () => {
  afterEach(() => jest.clearAllMocks());

  it('does not render cre.description on the CRE detail page', async () => {
    const secretDescription = 'SECRET_CRE_DESCRIPTION_MUST_NOT_RENDER';
    mockedAxios.get.mockResolvedValue({
      data: {
        data: {
          id: '111-111',
          name: 'Stored secrets',
          doctype: 'CRE',
          description: secretDescription,
          links: [],
        },
      },
    });

    const { container, queryByText, findByText } = render(
      <MemoryRouter initialEntries={['/cre/111-111']}>
        <Route path="/cre/:id">
          <CommonRequirementEnumeration />
        </Route>
      </MemoryRouter>
    );

    await findByText('Stored secrets');
    await waitFor(() => expect(mockedAxios.get).toHaveBeenCalled());
    expect(queryByText(secretDescription)).toBeNull();
    expect(container.querySelector('.cre-page__description')).toBeNull();
  });
});
