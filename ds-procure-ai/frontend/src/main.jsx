import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { createLogger, installGlobalErrorHandlers } from './shared/logger-global/index.js'

const log = createLogger('main')
installGlobalErrorHandlers(log.bind({ workflow: 'client.global' }))
log.info('Mate frontend starting')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
