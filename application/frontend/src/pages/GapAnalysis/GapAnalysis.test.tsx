import { act, render } from '@testing-library/react';
import axios from 'axios';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

import { GapAnalysis } from './GapAnalysis';

jest.mock('../../hooks/useEnvironment', () => ({
  useEnvironment: () => ({ name: 'test', apiUrl: '/rest/v1' }),
}));

jest.mock('../../utils', () => ({
  getDocumentDisplayName: (document: { name?: string }) => document.name ?? '',
}));

jest.mock('../../utils/document', () => ({
  getInternalUrl: () => '#',
}));

jest.mock('axios');

const mockGet = axios.get as jest.Mock;
const jobResultsUrl = '/rest/v1/ma_job_results?id=job-123';

const renderGapAnalysis = () =>
  render(
    <MemoryRouter initialEntries={['/map_analysis?base=ASVS&compare=CWE']}>
      <GapAnalysis />
    </MemoryRouter>
  );

const flushPromises = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};

const pollRequests = () => mockGet.mock.calls.filter(([url]) => url === jobResultsUrl);

describe('GapAnalysis background job polling', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockGet.mockImplementation((url: string) => {
      if (url === '/rest/v1/ga_standards') {
        return Promise.resolve({ data: ['ASVS', 'CWE'] });
      }
      if (url.startsWith('/rest/v1/map_analysis?')) {
        return Promise.resolve({ data: { job_id: 'job-123' } });
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  it('stops polling and displays the error when the background job fails', async () => {
    const { container } = renderGapAnalysis();
    await flushPromises();

    expect(mockGet).toHaveBeenCalledWith('/rest/v1/map_analysis?standard=ASVS&standard=CWE');
    expect(container.querySelector('.ui.loader')).not.toBeNull();

    mockGet.mockImplementation((url: string) => {
      if (url === jobResultsUrl) {
        return Promise.reject({
          response: { data: { message: 'Background job failed' } },
        });
      }
      return Promise.resolve({ data: ['ASVS', 'CWE'] });
    });

    await act(async () => {
      jest.advanceTimersByTime(10000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain('Background job failed');
    expect(container.querySelector('.ui.loader')).toBeNull();
    expect(pollRequests()).toHaveLength(1);

    await act(async () => {
      jest.advanceTimersByTime(20000);
      await Promise.resolve();
    });
    expect(pollRequests()).toHaveLength(1);
  });

  it('displays a network error without an HTTP response and stops polling', async () => {
    const { container } = renderGapAnalysis();
    await flushPromises();

    mockGet.mockImplementation((url: string) => {
      if (url === jobResultsUrl) {
        return Promise.reject(new Error('Network unavailable'));
      }
      return Promise.resolve({ data: ['ASVS', 'CWE'] });
    });

    await act(async () => {
      jest.advanceTimersByTime(10000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain('Network unavailable');
    expect(container.querySelector('.ui.loader')).toBeNull();
    expect(pollRequests()).toHaveLength(1);

    await act(async () => {
      jest.advanceTimersByTime(20000);
      await Promise.resolve();
    });
    expect(pollRequests()).toHaveLength(1);
  });

  it('stops polling and displays results after a successful response', async () => {
    const { container } = renderGapAnalysis();
    await flushPromises();

    mockGet.mockImplementation((url: string) => {
      if (url === jobResultsUrl) {
        return Promise.resolve({
          data: {
            result: {
              resultKey: {
                start: { doctype: 'standard', name: 'Analysis Result' },
                paths: {},
                extra: 0,
              },
            },
          },
        });
      }
      return Promise.resolve({ data: ['ASVS', 'CWE'] });
    });

    await act(async () => {
      jest.advanceTimersByTime(10000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain('Analysis Result');
    expect(container.querySelector('.ui.loader')).toBeNull();
    expect(pollRequests()).toHaveLength(1);

    await act(async () => {
      jest.advanceTimersByTime(20000);
      await Promise.resolve();
    });
    expect(pollRequests()).toHaveLength(1);
  });
});
