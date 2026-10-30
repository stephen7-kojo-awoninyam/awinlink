import { useCallback, useState, type Dispatch, type SetStateAction } from 'react';
import { preservePage } from '@/src/pagination';

export function usePagedState<T>(initial: T[]): [T[], Dispatch<SetStateAction<T[]>>] {
  const [items, setItems] = useState(initial);
  const update = useCallback<Dispatch<SetStateAction<T[]>>>(next => {
    setItems(previous => {
      if (typeof next !== 'function') return next;
      const result = next(previous);
      // A fetched/merged page carries its own continuation, including null.
      return Object.getOwnPropertySymbols(result).length ? result : preservePage(previous, result);
    });
  }, []);
  return [items, update];
}
