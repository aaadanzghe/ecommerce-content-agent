import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],server:{proxy:{'/api':{target:'http://127.0.0.1:8888',rewrite:p=>p.replace(/^\/api/,'')},'/media':'http://127.0.0.1:8888'}},test:{globals:true,environment:'jsdom',setupFiles:'./src/test/setup.ts'}});
