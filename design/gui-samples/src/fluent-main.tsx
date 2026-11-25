import {createRoot} from 'react-dom/client';
import {App} from './App';
import {FluentEditor} from './FluentEditor';
document.documentElement.dataset.variant = 'fluent';
createRoot(document.getElementById('root')!).render(<App variant="fluent" Editor={FluentEditor}/>);
