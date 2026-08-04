import { fireEvent, render, waitFor } from '@testing-library/react';
import React from 'react';

import { useCapabilities } from '../../hooks/useCapabilities';
import { useResourceSelection } from '../../hooks/useResourceSelection';
import { useUser } from '../../hooks/useUser';
import { ResourceSelector } from './ResourceSelector';

jest.mock('../../hooks/useEnvironment', () => ({
  useEnvironment: () => ({ name: 'test', apiUrl: '/rest/v1' }),
}));
jest.mock('../../hooks/useCapabilities');
jest.mock('../../hooks/useUser');
jest.mock('../../hooks/useResourceSelection');

const mockCaps = useCapabilities as jest.Mock;
const mockUser = useUser as jest.Mock;
const mockSel = useResourceSelection as jest.Mock;

function standardsFetch(list: string[]): jest.Mock {
  return jest.fn().mockResolvedValue({
    status: 200,
    ok: true,
    json: () => Promise.resolve(list),
  });
}

describe('ResourceSelector', () => {
  beforeEach(() => {
    mockCaps.mockReturnValue({
      capabilities: { myopencre: true, login: true },
      loading: false,
    });
    mockUser.mockReturnValue({
      user: 'u',
      isLoggedIn: true,
      loading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });
    mockSel.mockReturnValue({
      selected: ['ASVS'],
      loading: false,
      saving: false,
      error: null,
      save: jest.fn().mockResolvedValue(['ASVS']),
    });
    (global as any).fetch = standardsFetch(['ASVS', 'CWE', 'SAMM']);
  });

  // clearAllMocks (not resetAllMocks): keep the mock implementations across the
  // async boundary so a fetch that resolves after a test can't crash a leaked
  // render by making a mocked hook return undefined.
  afterEach(() => jest.clearAllMocks());

  it('fetches the full universe of standards with ?all=true', async () => {
    render(<ResourceSelector />);
    await waitFor(() => expect((global as any).fetch).toHaveBeenCalled());
    const url = (global as any).fetch.mock.calls[0][0] as string;
    expect(url).toContain('/standards?all=true');
  });

  it('pre-checks the standards in the current selection', async () => {
    const { container, findByText } = render(<ResourceSelector />);
    await findByText('Save');
    const inputs = container.querySelectorAll('input[type="checkbox"]');
    expect(inputs.length).toBe(3);
    expect((inputs[0] as HTMLInputElement).checked).toBe(true); // ASVS (selected)
    expect((inputs[1] as HTMLInputElement).checked).toBe(false); // CWE
    expect((inputs[2] as HTMLInputElement).checked).toBe(false); // SAMM
  });

  it('toggling a checkbox and clicking Save persists the updated list', async () => {
    const saveMock = jest.fn().mockResolvedValue(['ASVS', 'CWE']);
    mockSel.mockReturnValue({
      selected: ['ASVS'],
      loading: false,
      saving: false,
      error: null,
      save: saveMock,
    });
    const { container, findByText, getByText } = render(<ResourceSelector />);
    await findByText('Save');
    // semantic-ui-react <Checkbox> toggles when the event target is the input:
    // click the CWE input directly (index 1 in the fixed standards order).
    const inputs = container.querySelectorAll('input[type="checkbox"]');
    fireEvent.click(inputs[1] as HTMLElement); // add CWE
    fireEvent.click(getByText('Save'));
    await waitFor(() => expect(saveMock).toHaveBeenCalled());
    const arg = (saveMock.mock.calls[0][0] as string[]).slice().sort();
    expect(arg).toEqual(['ASVS', 'CWE']);
  });

  it('shows a success message after a successful save', async () => {
    const { findByText, getByText } = render(<ResourceSelector />);
    await findByText('Save');
    fireEvent.click(getByText('Save'));
    expect(await findByText(/saved/i)).toBeTruthy();
  });

  it('shows an error message when the hook reports an error', async () => {
    mockSel.mockReturnValue({
      selected: ['ASVS'],
      loading: false,
      saving: false,
      error: 'Could not save your standards. Please try again.',
      save: jest.fn(),
    });
    const { findByText } = render(<ResourceSelector />);
    expect(await findByText(/could not save/i)).toBeTruthy();
  });

  it('renders a login prompt (not the checklist) when logged out', async () => {
    mockUser.mockReturnValue({
      user: null,
      isLoggedIn: false,
      loading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });
    const { findByText, queryByText } = render(<ResourceSelector />);
    expect(await findByText(/log in/i)).toBeTruthy();
    expect(queryByText('Save')).toBeNull();
  });

  it('renders nothing when the MyOpenCRE capability is off', () => {
    mockCaps.mockReturnValue({
      capabilities: { myopencre: false, login: true },
      loading: false,
    });
    const { container } = render(<ResourceSelector />);
    expect(container.firstChild).toBeNull();
  });
});
