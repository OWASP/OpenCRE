// Add the imports for AI Mapping components
import { AIMapping } from './frontend/src/pages/AIMapping/AIMapping';
import { AIReview } from './frontend/src/pages/AIMapping/AIReview';
import { AIComplete } from './frontend/src/pages/AIMapping/AIComplete';

// Add these routes with the other route definitions
export const routes = [
  // ... existing routes

  // AI Mapping routes
  {
    path: '/myopencre/ai-map',
    Component: AIMapping,
    exact: true
  },
  {
    path: '/myopencre/ai-map/review',
    Component: AIReview,
    exact: true
  },
  {
    path: '/myopencre/ai-map/complete',
    Component: AIComplete,
    exact: true
  },

  // ... other existing routes
]; 