import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import Overlay from './Overlay.jsx';
import './styles.css';

const match = location.pathname.match(/^\/overlay\/([^/]+)\/?$/);
createRoot(document.getElementById('root')).render(match ? <Overlay id={decodeURIComponent(match[1])} /> : <App />);
