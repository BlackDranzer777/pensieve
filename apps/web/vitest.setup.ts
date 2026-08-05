import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});

/*
 * Environment shims.
 *
 * These are deliberately plain functions rather than `vi.fn()`. The Vitest
 * config sets `restoreMocks: true`, which resets every mock before each test —
 * that would strip the implementations below after the first test and make
 * them return `undefined`.
 */

// Recharts measures its container before rendering. jsdom reports every element
// as 0x0, so charts would render nothing and chart assertions would silently
// pass against an empty DOM.
class ResizeObserverStub implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver = ResizeObserverStub;

Object.defineProperty(globalThis.HTMLElement.prototype, 'getBoundingClientRect', {
  configurable: true,
  writable: true,
  value: function getBoundingClientRect(): DOMRect {
    return {
      width: 800,
      height: 400,
      top: 0,
      left: 0,
      right: 800,
      bottom: 400,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    };
  },
});

// jsdom does not implement matchMedia; the theme hook depends on it.
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  writable: true,
  value: function matchMedia(query: string): MediaQueryList {
    return {
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    };
  },
});
