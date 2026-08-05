import type { JSX } from 'react';

/**
 * Inline SVG icons.
 *
 * Hand-written rather than pulled from an icon package: the set is small, and
 * inlining keeps the bundle free of a dependency whose 1000+ unused glyphs
 * would need tree-shaking to justify.
 *
 * Every icon is `aria-hidden` — meaning comes from the adjacent text label, so
 * screen readers should not announce the glyph as well.
 */

export interface IconProps {
  className?: string;
}

function Icon({ className, path }: IconProps & { path: string }): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        d={path}
      />
    </svg>
  );
}

export function IconOverview(props: IconProps): JSX.Element {
  return <Icon {...props} path="M4 13h6V4H4zm10 7h6v-9h-6zM4 20h6v-3H4zM14 7h6V4h-6z" />;
}

export function IconBrands(props: IconProps): JSX.Element {
  return <Icon {...props} path="M4 20V10m5 10V5m5 15v-7m5 7V8" />;
}

export function IconTrends(props: IconProps): JSX.Element {
  return <Icon {...props} path="m3 16 5-6 4 3.5L21 6m0 0h-5m5 0v5" />;
}

export function IconReviews(props: IconProps): JSX.Element {
  return <Icon {...props} path="M4 5h16v11H9l-5 4z" />;
}

export function IconQuality(props: IconProps): JSX.Element {
  return (
    <Icon
      {...props}
      path="M12 3l7.5 3.5v5c0 4.4-3.1 8.4-7.5 9.5-4.4-1.1-7.5-5.1-7.5-9.5v-5zM9 12l2 2 4-4"
    />
  );
}

export function IconPipeline(props: IconProps): JSX.Element {
  return (
    <Icon
      {...props}
      path="M6 5h5a3 3 0 0 1 3 3v8a3 3 0 0 0 3 3h1M4.5 5a1.5 1.5 0 1 0 3 0 1.5 1.5 0 0 0-3 0Zm12 14a1.5 1.5 0 1 0 3 0 1.5 1.5 0 0 0-3 0Z"
    />
  );
}

export function IconMenu(props: IconProps): JSX.Element {
  return <Icon {...props} path="M4 7h16M4 12h16M4 17h16" />;
}

export function IconSun(props: IconProps): JSX.Element {
  return (
    <Icon
      {...props}
      path="M12 4V2m0 20v-2m8-8h2M2 12h2m13.7-5.7 1.4-1.4M4.9 19.1l1.4-1.4m0-11.4L4.9 4.9m14.2 14.2-1.4-1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z"
    />
  );
}

export function IconMoon(props: IconProps): JSX.Element {
  return <Icon {...props} path="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />;
}

export function IconDocument(props: IconProps): JSX.Element {
  return <Icon {...props} path="M5 4h9l5 5v11H5zM14 4v5h5" />;
}

export function IconLogo(props: IconProps): JSX.Element {
  return <Icon {...props} path="M12 3a9 9 0 1 0 9 9M12 7.5a4.5 4.5 0 1 0 4.5 4.5M21 3l-6.5 6.5" />;
}

export function IconList(props: IconProps): JSX.Element {
  return <Icon {...props} path="M4 7h16M4 12h10M4 17h7" />;
}

export function IconAlert(props: IconProps): JSX.Element {
  return (
    <Icon
      {...props}
      path="M12 8v5m0 3.5v.01M10.3 3.9 2.5 17.4A1.8 1.8 0 0 0 4 20h16a1.8 1.8 0 0 0 1.6-2.6L13.7 3.9a1.9 1.9 0 0 0-3.4 0Z"
    />
  );
}
