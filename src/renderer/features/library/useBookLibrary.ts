import { useCallback, useEffect, useMemo, useState } from "react";
import { getElectronApi } from "../../api/electronApi";
import type { BookLibraryState } from "../../api/types";

export function useBookLibrary() {
  const api = useMemo(() => getElectronApi(), []);
  const [library, setLibrary] = useState<BookLibraryState>({ books: [] });

  const refresh = useCallback(async () => {
    setLibrary(await api.app.library());
  }, [api]);

  const openBook = useCallback(async (bookId: string) => {
    await api.app.openBook(bookId);
    await refresh();
  }, [api, refresh]);

  const newBook = useCallback(async (title: string) => {
    await api.app.newBook(title);
    await refresh();
  }, [api, refresh]);

  useEffect(() => {
    refresh().catch(() => setLibrary({ books: [] }));
  }, [refresh]);

  return { library, refresh, openBook, newBook };
}
