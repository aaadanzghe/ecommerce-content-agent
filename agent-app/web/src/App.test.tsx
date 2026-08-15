import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

const result = { optimized_title: 'Optimized title', selling_points: ['Point one'], description: 'Description', social_copy: 'Social', seo_keywords: ['keyword'], quality_score: { accuracy: { score: 5 }, attractiveness: { score: 4 }, compliance: { score: 5 }, seo: { score: 4 }, total: 4.6, passed: true }, platform: 'taobao' };
beforeEach(() => { localStorage.clear(); vi.stubGlobal('fetch', vi.fn(async (input: string) => input.endsWith('/health') ? new Response('{"status":"ok"}', { status: 200 }) : new Response(JSON.stringify(result), { status: 200 }))); });

it('loads a sample and edits dynamic attributes', async () => { render(<App />); await userEvent.selectOptions(screen.getByLabelText('加载示例'), 'TWS Pro'); expect(screen.getByDisplayValue('TWS Pro 真无线主动降噪耳机')).toBeInTheDocument(); fireEvent.change(screen.getAllByLabelText('属性值')[0], { target: { value: '5.4' } }); expect(screen.getByDisplayValue('5.4')).toBeInTheDocument(); });
it('generates content and copies a result', async () => { render(<App />); await userEvent.type(screen.getByPlaceholderText('例如：TWS Pro 真无线主动降噪耳机'), 'Product'); await userEvent.click(screen.getByText('开始生成')); await waitFor(() => expect(screen.getByText('Optimized title')).toBeInTheDocument()); await userEvent.click(screen.getAllByTitle('复制')[0]); expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Optimized title'); });
it('switches to mobile result view after generation', async () => { render(<App />); await userEvent.click(screen.getByText('查看结果')); expect(screen.getByText('等待你的第一个内容任务')).toBeInTheDocument(); });
