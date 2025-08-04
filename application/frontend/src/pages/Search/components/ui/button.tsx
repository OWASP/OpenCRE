import './button.scss'; // Import the new SCSS file

import React from 'react';

// Define the types for button props
type ButtonVariant = 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link';
type ButtonSize = 'default' | 'sm' | 'lg' | 'icon';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => {
    // Build the className string based on props
    const classNames = [
      'btn',
      `btn--${variant}`,
      `btn--${size}`,
      className, // Allow passing additional custom classes
    ]
      .filter(Boolean)
      .join(' ');

    return <button className={classNames} ref={ref} {...props} />;
  }
);

Button.displayName = 'Button';

export { Button };
