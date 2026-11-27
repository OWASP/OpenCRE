import { render, waitFor } from '@testing-library/react';
import axios from 'axios';
import React from 'react';

import { Document } from '../../types';
import { SearchName } from './SearchName';

jest.mock('axios');
jest.mock('react-router-dom', () => ({
  useParams: () => ({ searchTerm: 'crypto' }),
}));
jest.mock('../../hooks', () => ({
  useEnvironment: () => ({ apiUrl: '/rest/v1' }),
}));
jest.mock('../../utils', () => ({
  scrollMountToTop: jest.fn(),
}));
jest.mock('./components/SearchResults', () => ({
  SearchResults: ({ results }: { results: Document[] }) => (
    <ul data-testid="search-results">
      {results.map((doc, idx) => (
        <li key={`${doc.doctype}-${doc.id ?? doc.name}-${idx}`}>{doc.name}</li>
      ))}
    </ul>
  ),
}));

const mockedAxiosGet = axios.get as jest.Mock;

const CRE_DOC: Document = {
  doctype: 'CRE',
  id: '170-772',
  name: 'Cryptography',
};

const STANDARD_DOC: Document = {
  doctype: 'Standard',
  name: 'ASVS',
  section: 'V6.1.1',
};

describe('SearchName', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows results for both categories when both CREs and sources match', async () => {
    mockedAxiosGet.mockResolvedValue({ data: [CRE_DOC, STANDARD_DOC] });
    const { findByText, queryByText } = render(<SearchName />);

    expect(await findByText('Cryptography')).toBeTruthy();
    expect(await findByText('ASVS')).toBeTruthy();
    expect(queryByText('No CREs match this search.')).toBeNull();
    expect(queryByText('No sources match this search.')).toBeNull();
  });

  it('shows an explicit empty state for sources when only CREs match', async () => {
    mockedAxiosGet.mockResolvedValue({ data: [CRE_DOC] });
    const { findByText, queryByText } = render(<SearchName />);

    expect(await findByText('Cryptography')).toBeTruthy();
    expect(await findByText('No sources match this search.')).toBeTruthy();
    expect(queryByText('No CREs match this search.')).toBeNull();
  });

  it('shows an explicit empty state for CREs when only sources match', async () => {
    mockedAxiosGet.mockResolvedValue({ data: [STANDARD_DOC] });
    const { findByText, queryByText } = render(<SearchName />);

    expect(await findByText('ASVS')).toBeTruthy();
    expect(await findByText('No CREs match this search.')).toBeTruthy();
    expect(queryByText('No sources match this search.')).toBeNull();
  });

  it('shows an overall empty state when neither category has results', async () => {
    mockedAxiosGet.mockResolvedValue({ data: [] });
    const { container, findByText, queryByText } = render(<SearchName />);

    expect(await findByText('No results match your search.')).toBeTruthy();
    expect(await findByText(/No CREs or sources were found for/)).toBeTruthy();
    expect(queryByText('Matching CREs')).toBeNull();
    expect(queryByText('Matching sources')).toBeNull();
    expect(container.querySelector('.ui.info.message')).toBeTruthy();
    expect(container.querySelector('.ui.negative.message')).toBeNull();
  });

  it('keeps loading and error states distinguishable from empty results', async () => {
    let rejectRequest!: (err: unknown) => void;
    mockedAxiosGet.mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectRequest = reject;
        })
    );

    const { container, findByText, queryByText } = render(<SearchName />);
    expect(container.querySelector('.ui.loader')).toBeTruthy();
    expect(queryByText('No results match your search.')).toBeNull();

    rejectRequest({ response: { status: 500 } });
    await waitFor(() => expect(container.querySelector('.ui.negative.message')).toBeTruthy());
    expect(await findByText('Document could not be loaded')).toBeTruthy();
    expect(queryByText('No results match your search.')).toBeNull();
  });
});
