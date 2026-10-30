import { useCallback, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { preservePage } from '@/src/pagination';

// Values disappear in the first render of a new identity/context. A setter held
// by an old asynchronous operation cannot populate the new identity's screen.
export function useScopedState<T>(scope: string, initial: T | (() => T)): [T, Dispatch<SetStateAction<T>>] {
  const current = useRef({ scope });
  if (current.current.scope !== scope) current.current = { scope };
  const identity = current.current;
  const initialValue = () => typeof initial === 'function' ? (initial as () => T)() : initial;
  const [snapshot, setSnapshot] = useState(() => ({ identity, value: initialValue() }));
  const setValue = useCallback<Dispatch<SetStateAction<T>>>((next) => {
    if (current.current !== identity) return;
    setSnapshot(previous => {
      if (current.current !== identity) return previous;
      const value = previous.identity === identity ? previous.value : initialValue();
      let result = typeof next === 'function' ? (next as (value: T) => T)(value) : next;
      if (typeof next === 'function' && Array.isArray(value) && Array.isArray(result)
          && !Object.getOwnPropertySymbols(result).length) result = preservePage(value, result) as T;
      return { identity, value: result };
    });
  }, [identity]);
  if (snapshot.identity !== identity) {
    const value = initialValue();
    setSnapshot({ identity, value });
    return [value, setValue];
  }
  return [snapshot.value, setValue];
}
