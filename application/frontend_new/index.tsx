import React from "react";
import { createRoot } from 'react-dom/client';

import {App} from './src/App';

createRoot(document.querySelector('#app') as HTMLElement).render(<App />);