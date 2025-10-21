import './toast.scss'; // Import the new SCSS file

import * as ToastPrimitives from '@radix-ui/react-toast';
import { X } from 'lucide-react';
import React from 'react';

// Re-export the provider from Radix UI
const ToastProvider = ToastPrimitives.Provider;

const ToastViewport = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Viewport>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Viewport>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Viewport
    ref={ref}
    className={['toast-viewport', className].filter(Boolean).join(' ')}
    {...props}
  />
));
ToastViewport.displayName = ToastPrimitives.Viewport.displayName;

type ToastVariant = 'default' | 'destructive';

interface ToastRootProps extends React.ComponentPropsWithoutRef<typeof ToastPrimitives.Root> {
  variant?: ToastVariant;
}

const Toast = React.forwardRef<React.ElementRef<typeof ToastPrimitives.Root>, ToastRootProps>(
  ({ className, variant = 'default', ...props }, ref) => {
    const classNames = ['toast', `toast--${variant}`, className].filter(Boolean).join(' ');

    return <ToastPrimitives.Root ref={ref} className={classNames} {...props} />;
  }
);
Toast.displayName = ToastPrimitives.Root.displayName;

const ToastAction = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Action>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Action>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Action
    ref={ref}
    className={['toast-action', className].filter(Boolean).join(' ')}
    {...props}
  />
));
ToastAction.displayName = ToastPrimitives.Action.displayName;

const ToastClose = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Close>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Close>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Close
    ref={ref}
    className={['toast-close', className].filter(Boolean).join(' ')}
    toast-close="" // Radix UI uses this attribute for functionality
    {...props}
  >
    <X />
  </ToastPrimitives.Close>
));
ToastClose.displayName = ToastPrimitives.Close.displayName;

const ToastTitle = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Title>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Title>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Title
    ref={ref}
    className={['toast-title', className].filter(Boolean).join(' ')}
    {...props}
  />
));
ToastTitle.displayName = ToastPrimitives.Title.displayName;

const ToastDescription = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Description>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Description>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Description
    ref={ref}
    className={['toast-description', className].filter(Boolean).join(' ')}
    {...props}
  />
));
ToastDescription.displayName = ToastPrimitives.Description.displayName;

type ToastProps = React.ComponentPropsWithoutRef<typeof Toast>;
type ToastActionElement = React.ReactElement<typeof ToastAction>;

// --- START OF CORRECTION ---

// First, export the types using a dedicated 'export type' statement.
// This is the cleanest way to export only types.
export type { ToastProps, ToastActionElement };

// Second, export the components (values) in a separate statement.
export { ToastProvider, ToastViewport, Toast, ToastTitle, ToastDescription, ToastClose, ToastAction };

// --- END OF CORRECTION ---
