import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { BrainstormJSON } from "@/hooks/useBrainstorm";

interface Props {
  brainstorm: BrainstormJSON | null;
}

// --- helpers to coerce shapes safely ---
function toList(v: unknown): string[] {
  if (Array.isArray(v)) return v.filter(Boolean).map(String);
  if (typeof v === "string") {
    // split on commas / newlines / bullets if a single string slipped through
    return v
      .split(/[\n,•]+/)
      .map(s => s.trim())
      .filter(Boolean);
  }
  return [];
}

function toDict(v: unknown): Record<string, string> {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, string>;
  }
  if (Array.isArray(v)) {
    // allow ["width: 40 mm", "height: 20 mm"] style arrays
    const out: Record<string, string> = {};
    v.forEach((item, i) => {
      const s = String(item);
      const idx = i + 1;
      if (s.includes(":")) {
        const [k, ...rest] = s.split(":");
        out[k.trim() || `Item ${idx}`] = rest.join(":").trim();
      } else {
        out[`Item ${idx}`] = s;
      }
    });
    return out;
  }
  return {};
}

export default function BrainstormView({ brainstorm }: Props) {
  if (!brainstorm) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        ← Submit a prompt to start brainstorming
      </div>
    );
  }

  // If the backend returned raw text (invalid JSON from the model), show it nicely.
  if ((brainstorm as any)._raw) {
    return (
      <ScrollArea className="h-full pr-4">
        <Card className="mb-4 bg-background">
          <CardHeader>
            <CardTitle className="text-base">Brainstorm (raw)</CardTitle>
            <CardDescription>
              The model returned invalid JSON. Here’s the raw output for reference.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm">
              {(brainstorm as any)._raw}
            </pre>
          </CardContent>
        </Card>
      </ScrollArea>
    );
  }

  // Coerce fields to safe shapes
  const oneLiner =
    typeof (brainstorm as any).design_one_liner === "string"
      ? (brainstorm as any).design_one_liner
      : String((brainstorm as any).design_one_liner ?? "");

  const features         = toList((brainstorm as any).key_features);
  const functionalities  = toList((brainstorm as any).key_functionalities);
  const components       = toList((brainstorm as any).design_components);
  const geometry         = toDict((brainstorm as any).optimal_geometry);

  const sections = [
    { title: "Key Features",        list: features },
    { title: "Key Functionalities", list: functionalities },
    { title: "Design Components",   list: components },
  ] as const;

  return (
    <ScrollArea className="h-full pr-4">
      {/* one-liner on top */}
      <Card className="mb-4 bg-background">
        <CardHeader>
          <CardTitle className="text-base">Design One-Liner</CardTitle>
        </CardHeader>
        <CardContent>
          <CardDescription>{oneLiner || "—"}</CardDescription>
        </CardContent>
      </Card>

      {/* grid for everything else */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sections.map(({ title, list }) => (
          <Card key={title} className="bg-background">
            <CardHeader>
              <CardTitle className="text-base">{title}</CardTitle>
            </CardHeader>
            <CardContent>
              {list.length ? (
                <ul className="list-disc pl-5 space-y-1">
                  {list.map((item, i) => (
                    <li key={`${title}-${i}`}>{item}</li>
                  ))}
                </ul>
              ) : (
                <div className="text-sm text-muted-foreground">No items</div>
              )}
            </CardContent>
          </Card>
        ))}

        {/* key-value section */}
        <Card className="bg-background">
          <CardHeader>
            <CardTitle className="text-base">Optimal Geometry</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(geometry).length ? (
              <ul className="pl-0 space-y-1">
                {Object.entries(geometry).map(([k, v]) => (
                  <li key={k} className="flex justify-between gap-4">
                    <span className="font-medium">{k}</span>
                    <span className="truncate">{String(v)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-sm text-muted-foreground">No geometry provided</div>
            )}
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  );
}
