import { defineCollection, z } from 'astro:content';

const blogCollection = defineCollection({
  type: 'content', // Это значит, что файлы .mdx
  schema: z.object({
    title: z.string(),
    description: z.string(),
    image: z.string().optional(),
    date: z.date().optional(),
    // Можно добавить теги, автора и т.д.
  }),
});

export const collections = {
  'blog': blogCollection,
};