import { z } from 'zod';

/**
 * The pagination envelope every list endpoint returns.
 *
 * Mirrors `PageMeta` / `Page[T]` in apps/api/app/schemas/common.py.
 */
export const pageMetaSchema = z.object({
  page: z.number().int(),
  page_size: z.number().int(),
  total_items: z.number().int(),
  total_pages: z.number().int(),
  has_next: z.boolean(),
  has_previous: z.boolean(),
});

export type PageMeta = z.infer<typeof pageMetaSchema>;

/**
 * Wrap an item schema in the paged envelope.
 *
 * A function rather than a generic type because Zod schemas are values: the
 * item schema has to be passed at runtime for `items` to be validated at all.
 */
export function pageSchema<TItem extends z.ZodTypeAny>(
  item: TItem,
): z.ZodType<Page<z.infer<TItem>>> {
  // Annotated as `ZodType<Page<…>>` rather than the inferred `ZodObject<…>`:
  // ZodObject carries four more type parameters that would have to be spelled
  // out correctly here, and callers only ever need the parsed shape.
  return z.object({ items: z.array(item), meta: pageMetaSchema });
}

export interface Page<TItem> {
  items: TItem[];
  meta: PageMeta;
}
