import './input.scss'; // Import the new SCSS file

import React from 'react';

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(
  ({ className, type, ...props }, ref) => {
    // Combine the base class with any additional classes passed in props
    const classNames = ['input', className].filter(Boolean).join(' ');

    return <input type={type} className={classNames} ref={ref} {...props} />;
  }
);

Input.displayName = 'Input';

export { Input };
