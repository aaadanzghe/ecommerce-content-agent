import {vi} from 'vitest';import '@testing-library/jest-dom/vitest';Object.assign(navigator,{clipboard:{writeText:vi.fn()}});URL.createObjectURL=vi.fn(()=> 'blob:test');URL.revokeObjectURL=vi.fn();
