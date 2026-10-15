import { App } from './App.jsx';

let embedded = null;
try {
  const el = document.getElementById('radar-report');
  embedded = JSON.parse((el && el.textContent) || 'null');
} catch (e) {
  embedded = null;
}
ReactDOM.createRoot(document.getElementById('app')).render(<App embedded={embedded} />);
