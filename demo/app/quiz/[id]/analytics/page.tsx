"use client";

import { useParams, useRouter } from "next/navigation";
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useEffect, useState, useRef, useMemo } from "react";
import { Quiz, KnowledgeGraph, KnowledgeGraphEntity } from "@/lib/types";
import { Card } from "@/components/ui/card";
import {
  Lightbulb,
  User,
  Building2,
  MapPin,
  Box,
  Brain,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useTheme } from "next-themes";
import cytoscape, { Core } from "cytoscape";

// Helper function to convert snake_case to Title Case
function formatSnakeCase(str: string): string {
  if (!str) return "";
  return str.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

// Helper function to format attribute values
function formatAttributeValue(
  value: string | number | boolean | string[]
): string {
  if (Array.isArray(value)) {
    return value.map((v) => formatSnakeCase(String(v))).join(", ");
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return formatSnakeCase(String(value));
}

// Get icon for entity type
function getEntityIcon(type: string) {
  switch (type) {
    case "person":
      return User;
    case "organization":
      return Building2;
    case "location":
      return MapPin;
    case "thing":
      return Box;
    case "concept":
      return Brain;
    default:
      return Box;
  }
}

// Get color for entity type (using CSS variables)
function getEntityColor(type: string): string {
  switch (type) {
    case "person":
      return "hsl(var(--chart-1))"; // chart-1
    case "organization":
      return "hsl(var(--chart-4))"; // chart-4
    case "location":
      return "hsl(var(--chart-2))"; // chart-2
    case "thing":
      return "hsl(var(--chart-5))"; // chart-5
    case "concept":
      return "hsl(var(--chart-3))"; // chart-3
    default:
      return "hsl(var(--muted-foreground))"; // muted-foreground
  }
}

// Entity Icon Component (extracted to avoid creating during render)
function EntityIconDisplay({ type }: { type: string }) {
  const iconProps = { className: "w-5 h-5" };

  switch (type) {
    case "person":
      return <User {...iconProps} />;
    case "organization":
      return <Building2 {...iconProps} />;
    case "location":
      return <MapPin {...iconProps} />;
    case "thing":
      return <Box {...iconProps} />;
    case "concept":
      return <Brain {...iconProps} />;
    default:
      return <Box {...iconProps} />;
  }
}

// Entity Card Component
function EntityCard({
  entity,
  isExpanded,
  onToggle,
}: {
  entity: KnowledgeGraphEntity;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const hasAttributes =
    entity.attributes && Object.keys(entity.attributes).length > 0;

  const entityColor = getEntityColor(entity.type);

  return (
    <div
      className="group relative overflow-hidden rounded-xl border 
                 bg-linear-to-br from-card to-muted/30
                 hover:shadow-lg hover:shadow-primary/10
                 transition-all duration-300"
    >
      <div
        className="absolute inset-0 opacity-5"
        style={{ backgroundColor: entityColor }}
      />
      <div
        className="p-4 cursor-pointer relative"
        onClick={hasAttributes ? onToggle : undefined}
      >
        <div className="flex items-start gap-3">
          <div
            className="p-2 rounded-lg"
            style={{
              backgroundColor: `color-mix(in srgb, ${entityColor} 15%, transparent)`,
              color: entityColor,
            }}
          >
            <EntityIconDisplay type={entity.type} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <h4 className="font-semibold text-foreground truncate">
                {entity.name}
              </h4>
              {hasAttributes && (
                <button className="p-1 rounded-md hover:bg-muted transition-colors">
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              )}
            </div>
            <span
              className="text-xs font-medium px-2 py-0.5 rounded-full inline-block mt-1"
              style={{
                backgroundColor: `color-mix(in srgb, ${entityColor} 10%, transparent)`,
                color: entityColor,
              }}
            >
              {formatSnakeCase(entity.type)}
            </span>
          </div>
        </div>

        {/* Expandable attributes */}
        {hasAttributes && isExpanded && (
          <div className="mt-4 pt-3 border-t border-border">
            <div className="space-y-2">
              {Object.entries(entity.attributes).map(([key, value]) => (
                <div key={key} className="flex flex-col">
                  <span className="text-xs text-muted-foreground uppercase tracking-wide">
                    {formatSnakeCase(key)}
                  </span>
                  <span className="text-sm text-foreground/90">
                    {formatAttributeValue(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Knowledge Graph Visualization Component
function KnowledgeGraphVisualization({
  knowledgeGraph,
}: {
  knowledgeGraph: KnowledgeGraph;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const { theme } = useTheme();
  const [isDark, setIsDark] = useState(false);

  // Get color CSS variable name for entity type
  const getEntityColorVar = (type: string): string => {
    switch (type) {
      case "person":
        return "--chart-1";
      case "organization":
        return "--chart-4";
      case "location":
        return "--chart-2";
      case "thing":
        return "--chart-5";
      case "concept":
        return "--chart-3";
      default:
        return "--muted-foreground";
    }
  };

  // Get computed color values from CSS variables
  const getComputedColor = (cssVar: string): string => {
    if (typeof window === "undefined") return "#666";
    const computed = getComputedStyle(document.documentElement)
      .getPropertyValue(cssVar)
      .trim();
    // Convert hsl to rgb if needed (Cytoscape prefers rgb/hex)
    if (computed) {
      // Create a temporary element to get computed color
      const temp = document.createElement("div");
      temp.style.color = `hsl(${computed})`;
      document.body.appendChild(temp);
      const rgb = getComputedStyle(temp).color;
      document.body.removeChild(temp);
      return rgb;
    }
    return "#666";
  };

  // Memoize graph elements to prevent unnecessary recalculations
  const elements = useMemo(() => {
    // Create a Set of entity names that exist in entities field for quick lookup
    const validEntityNames = new Set<string>();
    const entityMap = new Map<string, KnowledgeGraphEntity>();
    knowledgeGraph.entities.forEach((entity) => {
      validEntityNames.add(entity.name);
      entityMap.set(entity.name, entity);
    });

    // Filter relationships: only include those where BOTH source and target exist in entities field
    const validRelationships = knowledgeGraph.relationships.filter(
      (rel) => validEntityNames.has(rel.source) && validEntityNames.has(rel.target)
    );

    // Collect entity names that participate in valid relationships
    const relationshipEntities = new Set<string>();
    validRelationships.forEach((rel) => {
      relationshipEntities.add(rel.source);
      relationshipEntities.add(rel.target);
    });

    // Only create nodes for entities that:
    // 1. Exist in entities field AND
    // 2. Participate in at least one valid relationship
    const nodes = Array.from(relationshipEntities)
      .filter((entityName) => validEntityNames.has(entityName))
      .map((entityName) => {
        const entity = entityMap.get(entityName);
        return {
          data: {
            id: entityName,
            label: entityName,
            type: entity?.type || "thing",
          },
        };
      });

    // Create edges only from valid relationships
    const edges = validRelationships.map((rel, idx) => ({
      data: {
        id: `edge-${idx}`,
        source: rel.source,
        target: rel.target,
        label: formatSnakeCase(rel.action),
      },
    }));

    return [...nodes, ...edges];
  }, [knowledgeGraph]);

  // Detect dark mode
  useEffect(() => {
    const checkDarkMode = () => {
      if (typeof window !== "undefined") {
        const isDarkMode =
          theme === "dark" ||
          (theme === "system" &&
            window.matchMedia("(prefers-color-scheme: dark)").matches);
        setIsDark(isDarkMode);
      }
    };
    checkDarkMode();
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    mediaQuery.addEventListener("change", checkDarkMode);
    return () => mediaQuery.removeEventListener("change", checkDarkMode);
  }, [theme]);

  useEffect(() => {
    // Wait for container to be ready and ensure it's mounted
    if (!containerRef.current || elements.length === 0) return;

    // Small delay to ensure DOM is ready
    const timeoutId = setTimeout(() => {
      if (!containerRef.current) return;

      // Destroy previous instance if exists
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }

      try {
        cyRef.current = cytoscape({
          container: containerRef.current,
          elements,
          style: [
            {
              selector: "node",
              style: {
                label: "data(label)",
                "text-valign": "bottom",
                "text-halign": "center",
                "text-margin-y": 8,
                "font-size": "11px",
                "font-weight": 500,
                color: getComputedColor("--muted-foreground"),
                "background-color": (ele) =>
                  getComputedColor(getEntityColorVar(ele.data("type"))),
                width: 40,
                height: 40,
                "border-width": 3,
                "border-color": getComputedColor("--background"),
                "text-max-width": "80px",
                "text-wrap": "ellipsis",
              },
            },
            {
              selector: "edge",
              style: {
                label: "data(label)",
                "curve-style": "bezier",
                "target-arrow-shape": "triangle",
                "target-arrow-color": getComputedColor("--muted"),
                "line-color": getComputedColor("--border"),
                width: 2,
                "font-size": "10px",
                color: getComputedColor("--muted-foreground"),
                "text-rotation": "autorotate",
                "text-margin-y": -10,
              },
            },
            {
              selector: "node:selected",
              style: {
                "border-width": 4,
                "border-color": getComputedColor("--primary"),
              },
            },
          ],
          layout: {
            name: "cose",
            animate: true,
            animationDuration: 500,
            nodeRepulsion: () => 8000,
            idealEdgeLength: () => 100,
            padding: 50,
          },
          minZoom: 0.3,
          maxZoom: 3,
          wheelSensitivity: 0.3,
        });
      } catch (error) {
        console.error("Error initializing Cytoscape:", error);
      }
    }, 100);

    return () => {
      clearTimeout(timeoutId);
      if (cyRef.current) {
        try {
          cyRef.current.destroy();
        } catch (error) {
          console.error("Error destroying Cytoscape:", error);
        }
        cyRef.current = null;
      }
    };
  }, [elements, isDark]);

  if (elements.length === 0) {
    return (
      <div className="flex items-center justify-center h-[400px] text-muted-foreground">
        No graph data available
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`w-full h-[400px] rounded-lg ${
        isDark ? "bg-zinc-900" : "bg-muted/30"
      }`}
    />
  );
}

export default function QuizAnalyticsPage() {
  const params = useParams();
  const router = useRouter();
  const quizId = params.id as string;
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [expandedEntities, setExpandedEntities] = useState<Set<string>>(
    new Set()
  );

  useEffect(() => {
    if (!quizId) return;
    const unsubscribe = onSnapshot(doc(db, "quizzes", quizId), (doc) => {
      if (doc.exists()) {
        const quizData = { id: doc.id, ...doc.data() } as Quiz;
        setQuiz(quizData);

        // Redirect if AI analytics not enabled
        if (!quizData.aiAnalyticsEnabled) {
          router.push(`/quiz/${quizId}`);
        }
      }
    });
    return () => unsubscribe();
  }, [quizId, router]);

  const toggleEntity = (entityName: string) => {
    setExpandedEntities((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(entityName)) {
        newSet.delete(entityName);
      } else {
        newSet.add(entityName);
      }
      return newSet;
    });
  };

  if (!quiz || !quiz.knowledgeGraph) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center text-muted-foreground">
          <Brain className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No AI analytics data available</p>
        </div>
      </div>
    );
  }

  const kg = quiz.knowledgeGraph;

  return (
    <div className="space-y-8">
      {/* Main Points */}
      {kg.context.mainPoints && kg.context.mainPoints.length > 0 && (
        <Card className="p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2 text-lg">
            <Lightbulb className="w-5 h-5 text-warning" />
            Main Points
          </h3>
          <ul className="space-y-3">
            {kg.context.mainPoints.map((point, idx) => (
              <li key={idx} className="flex items-start gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-warning/15 text-warning flex items-center justify-center text-sm font-medium">
                  {idx + 1}
                </span>
                <span className="text-foreground/90 leading-relaxed">
                  {point}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Knowledge Graph Visualization */}
      <Card className="p-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2 text-lg">
          <Brain className="w-5 h-5 text-chart-4" />
          Knowledge Graph
        </h3>
        <KnowledgeGraphVisualization knowledgeGraph={kg} />

        {/* Legend */}
        <div className="mt-4 pt-4 border-t border-border">
          <div className="flex flex-wrap gap-4 justify-center">
            {["person", "organization", "location", "thing", "concept"].map(
              (type) => {
                const Icon = getEntityIcon(type);
                return (
                  <div key={type} className="flex items-center gap-2 text-sm">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: getEntityColor(type) }}
                    />
                    <Icon className="w-4 h-4 text-muted-foreground" />
                    <span className="text-muted-foreground">
                      {formatSnakeCase(type)}
                    </span>
                  </div>
                );
              }
            )}
          </div>
        </div>
      </Card>

      {/* Entities Grid */}
      {kg.entities && kg.entities.length > 0 && (
        <div>
          <h3 className="font-semibold mb-4 flex items-center gap-2 text-lg">
            <Box className="w-5 h-5 text-chart-5" />
            Entities
            <span className="text-sm font-normal text-muted-foreground">
              ({kg.entities.length})
            </span>
          </h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {kg.entities.map((entity) => (
              <EntityCard
                key={entity.name}
                entity={entity}
                isExpanded={expandedEntities.has(entity.name)}
                onToggle={() => toggleEntity(entity.name)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Relationships as subtle connections */}
      {kg.relationships && kg.relationships.length > 0 && (
        <Card className="p-6">
          <h3 className="font-semibold mb-4 text-lg">Relationships</h3>
          <div className="space-y-2">
            {kg.relationships.map((rel, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2 text-sm py-2 px-3 rounded-lg bg-muted/50"
              >
                <span className="font-medium text-foreground">
                  {rel.source}
                </span>
                <span className="px-2 py-0.5 rounded bg-primary/10 text-primary text-xs">
                  {formatSnakeCase(rel.action)}
                </span>
                <span className="font-medium text-foreground">
                  {rel.target}
                </span>
                {rel.context && (
                  <span className="text-muted-foreground text-xs ml-2 italic">
                    ({rel.context})
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
