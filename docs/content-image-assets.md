# Content Image Assets

Use this workflow for static storefront/content images that are committed under
`web/public/img`, for example blog heroes, service illustrations, homepage
backgrounds, brand visuals, and one-off editorial assets.

Do not use it for catalog product uploads or product gallery variants. Product
media still belongs to the backend upload/optimizer/storage pipeline documented
in `docs/media-storage-r2.md`, because those files are tied to database rows,
variant approval state, and future R2/CDN product delivery.

## Optimize A New Asset

Run from `web/`:

```bash
npm run image:content -- optimize --input ~/Downloads/article-hero.png --namespace blog --slug article-hero --max-width 1600 --max-height 1200
```

The script writes a metadata-stripped WebP file to:

```text
web/public/img/<namespace>/<slug>.webp
```

Available namespaces are intentionally filesystem folders, not database
entities. Current recommended values are:

- `blog`
- `service`
- `hero`
- `brand`

Useful options:

- `--dry-run` processes the image and prints output dimensions/size without
  writing files.
- `--avif` writes an additional AVIF variant when the page is ready to reference
  one.
- `--hash` appends an 8-character content hash to the filename.
- `--overwrite` replaces an existing output after an explicit operator choice.

After optimizing, point the Astro/MDX/frontmatter reference at the new public
path, for example:

```yaml
image: "/img/blog/article-hero.webp"
```

## Audit Existing Assets

Run from `web/`:

```bash
npm run image:audit
```

The default audit is report-only and exits successfully. It flags PNG/JPEG
files above 500 KB, WebP/AVIF files above 350 KB, and raster assets with either
edge above 2400 px. Use stricter thresholds locally if needed:

```bash
npm run image:audit -- --max-size-kb 350 --max-webp-kb 250 --max-edge 2000
```

CI can later use the same command with `--fail-on-issues` after the existing
asset tree has been reviewed or migrated in small batches.

## Boundary With Product Media

Static content assets:

- live in `web/public/img`;
- are referenced directly by Astro, MDX frontmatter, CSS, or Vue components;
- are committed with the web app;
- should be optimized with `npm run image:content`.

Product media:

- lives under `/media/...` and database-backed product fields/variant rows;
- may use local storage or S3-compatible/R2 storage adapters;
- is generated and approved through backend product image services;
- should not be overwritten by this script.

Future R2/CDN work can reuse the same content conventions by adding a
content-assets object prefix such as `content/<namespace>/<slug>.<ext>`, but the
first safe step is a deterministic local optimization workflow before commit.
