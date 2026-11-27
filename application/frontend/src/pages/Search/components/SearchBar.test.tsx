import { fireEvent, render } from '@testing-library/react';
import React from 'react';
import { useHistory } from 'react-router-dom';

import { SearchBar } from './SearchBar';

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useHistory: jest.fn(),
}));

const mockUseHistory = useHistory as jest.Mock;

describe('SearchBar', () => {
  it('encodes special characters like % and # in the search URL', () => {
    const push = jest.fn();
    mockUseHistory.mockReturnValue({ push });

    const { getByLabelText } = render(<SearchBar />);
    const input = getByLabelText('Search OpenCRE');

    fireEvent.change(input, { target: { value: 'C#' } });
    fireEvent.submit(input.closest('form')!);
    expect(push).toHaveBeenCalledWith('/search/C%23');

    fireEvent.change(input, { target: { value: '100%' } });
    fireEvent.submit(input.closest('form')!);
    expect(push).toHaveBeenCalledWith('/search/100%25');
  });
});
