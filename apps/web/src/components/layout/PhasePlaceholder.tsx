import type { JSX } from 'react';

import { Card, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

interface PhasePlaceholderProps {
  title: string;
  phase: number;
  /** What this page will show once built. Stated concretely, not vaguely. */
  willShow: readonly string[];
}

/**
 * An honest "not built yet" panel.
 *
 * The alternative — shipping a page full of invented numbers — would make the
 * dashboard look finished while being a lie. This states plainly what is
 * missing and which phase delivers it.
 */
export function PhasePlaceholder({ title, phase, willShow }: PhasePlaceholderProps): JSX.Element {
  return (
    <Card className="mx-auto max-w-2xl">
      <CardBody className="space-y-4">
        <div className="flex items-center gap-2">
          <Badge tone="accent">Phase {phase}</Badge>
          <span className="text-xs text-ink-muted">Not built yet</span>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          <p className="mt-1 text-xs text-ink-muted">
            This page is delivered in build phase {phase}. It is shown in the navigation now so the
            application shell can be reviewed end to end — no placeholder metrics are displayed,
            because inventing numbers here would misrepresent what the platform has actually
            measured.
          </p>
        </div>

        <div>
          <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
            Planned content
          </p>
          <ul className="mt-2 space-y-1.5">
            {willShow.map((item) => (
              <li key={item} className="flex items-start gap-2 text-xs text-ink-muted">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-subtle" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </CardBody>
    </Card>
  );
}
