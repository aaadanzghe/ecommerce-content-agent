/** Browser entry point that mounts the single-page ecommerce Agent workspace. */
import React from 'react';import{createRoot}from'react-dom/client';import{BrowserRouter,Routes,Route,Navigate}from'react-router-dom';import App from'./App';import'./styles.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><BrowserRouter><Routes><Route path="/" element={<App/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></BrowserRouter></React.StrictMode>);
