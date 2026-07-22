import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import WaitlistLanding from '../src/app/page';

// Mock fetch globally
global.fetch = jest.fn() as jest.Mock;

describe('WaitlistLanding Page', () => {
  beforeEach(() => {
    (global.fetch as jest.Mock).mockClear();
  });

  it('renders the hero title correctly', () => {
    render(<WaitlistLanding />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/The Future of Behavioral Blockchain/i);
  });

  it('handles a successful form submission', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
    });

    render(<WaitlistLanding />);
    
    const emailInput = screen.getByLabelText(/Email address/i);
    const submitButton = screen.getByRole('button', { name: /Join Waitlist/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.click(submitButton);

    expect(screen.getByRole('button', { name: /Joining.../i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Welcome to the future. You are on the list./i)).toBeInTheDocument();
    });

    expect(global.fetch).toHaveBeenCalledWith('/api/waitlist', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ email: 'test@example.com' })
    }));
  });

  it('handles a failed form submission', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
    });

    render(<WaitlistLanding />);
    
    const emailInput = screen.getByLabelText(/Email address/i);
    const submitButton = screen.getByRole('button', { name: /Join Waitlist/i });

    fireEvent.change(emailInput, { target: { value: 'error@example.com' } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/Something went wrong. Please try again./i)).toBeInTheDocument();
    });
  });
});
