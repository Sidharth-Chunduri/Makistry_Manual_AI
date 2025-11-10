// src/pages/Project.tsx
import Index from "./Index";
import { useParams } from "react-router-dom";

export default function ProjectPage() {
  const { pid } = useParams<{ pid: string }>();
  return <Index existingProjectId={pid!} />;
}