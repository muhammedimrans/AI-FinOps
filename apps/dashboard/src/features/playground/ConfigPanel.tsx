import { Cpu, Settings2, Terminal } from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import CollapsibleSection from "./CollapsibleSection";
import ProviderInfoCard from "./ProviderInfoCard";
import { formatNumber } from "../../utils";
import type { PlaygroundConnectionOption, PlaygroundModelInfo } from "../../services/api";

interface ProjectOption {
  id: string;
  name: string;
}

interface ConfigPanelProps {
  connections: PlaygroundConnectionOption[];
  activeConnectionId: string;
  onConnectionChange: (id: string) => void;
  models: PlaygroundModelInfo[];
  modelsLoading: boolean;
  activeModelId: string;
  onModelChange: (id: string) => void;
  activeConnection: PlaygroundConnectionOption | undefined;
  activeModel: PlaygroundModelInfo | undefined;
  isPersonal: boolean;
  projectId: string;
  onProjectChange: (id: string) => void;
  projects: ProjectOption[];
  temperature: number;
  onTemperatureChange: (n: number) => void;
  topP: number;
  onTopPChange: (n: number) => void;
  maxTokens: number;
  onMaxTokensChange: (n: number) => void;
  systemPrompt: string;
  onSystemPromptChange: (s: string) => void;
}

/** Redesign goal #5 — the right-side configuration panel, rebuilt as three
 * compact, collapsible sections instead of three always-open cards. */
export default function ConfigPanel({
  connections,
  activeConnectionId,
  onConnectionChange,
  models,
  modelsLoading,
  activeModelId,
  onModelChange,
  activeConnection,
  activeModel,
  isPersonal,
  projectId,
  onProjectChange,
  projects,
  temperature,
  onTemperatureChange,
  topP,
  onTopPChange,
  maxTokens,
  onMaxTokensChange,
  systemPrompt,
  onSystemPromptChange,
}: ConfigPanelProps) {
  return (
    <div className="flex flex-col gap-3">
      <CollapsibleSection title="Provider &amp; model" icon={Cpu} defaultOpen>
        <div className="flex flex-col gap-3 pt-3">
          <ProviderInfoCard connection={activeConnection} model={activeModel} />

          <div>
            <label htmlFor="playground-connection" className="text-[11px] text-tx-muted mb-1 block">
              Provider connection
            </label>
            <div className="flex items-center gap-2">
              <ProviderLogo providerId={activeConnection?.provider_type ?? ""} size="sm" />
              <select
                id="playground-connection"
                value={activeConnectionId}
                onChange={(e) => onConnectionChange(e.target.value)}
                className="flex-1 rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
              >
                {connections.map((c) => (
                  <option key={c.id} value={c.id} disabled={!c.has_credential && c.provider_type !== "ollama"}>
                    {c.display_name}
                    {!c.has_credential && c.provider_type !== "ollama" ? " (no credential — connect first)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="playground-model" className="text-[11px] text-tx-muted mb-1 block">
              Model
            </label>
            <select
              id="playground-model"
              value={activeModelId}
              onChange={(e) => onModelChange(e.target.value)}
              disabled={modelsLoading || models.length === 0}
              className="w-full rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                  {m.is_deprecated ? " (deprecated)" : ""}
                </option>
              ))}
            </select>
            {activeModel && (
              <p className="text-[10px] text-tx-muted mt-1">
                {activeModel.context_window ? `${formatNumber(activeModel.context_window)} ctx` : ""}
                {activeModel.capabilities.length > 0 ? ` · ${activeModel.capabilities.join(", ")}` : ""}
              </p>
            )}
          </div>

          {!isPersonal && (
            <div>
              <label htmlFor="playground-project" className="text-[11px] text-tx-muted mb-1 block">
                Project (optional)
              </label>
              <select
                id="playground-project"
                value={projectId}
                onChange={(e) => onProjectChange(e.target.value)}
                className="w-full rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
              >
                <option value="">No project</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Advanced parameters"
        icon={Settings2}
        defaultOpen={false}
        summary={`Temp ${temperature.toFixed(1)} · Top P ${topP.toFixed(1)} · Max ${maxTokens}`}
      >
        <div className="flex flex-col gap-3 pt-3">
          <div>
            <label className="flex items-center justify-between text-[11px] text-tx-muted mb-1">
              Temperature <span className="font-mono">{temperature.toFixed(2)}</span>
            </label>
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={temperature}
              onChange={(e) => onTemperatureChange(Number(e.target.value))}
              aria-label="Temperature"
              className="w-full"
            />
          </div>
          <div>
            <label className="flex items-center justify-between text-[11px] text-tx-muted mb-1">
              Top P <span className="font-mono">{topP.toFixed(2)}</span>
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={topP}
              onChange={(e) => onTopPChange(Number(e.target.value))}
              aria-label="Top P"
              className="w-full"
            />
          </div>
          <div>
            <label htmlFor="playground-max-tokens" className="text-[11px] text-tx-muted mb-1 block">
              Max tokens
            </label>
            <input
              id="playground-max-tokens"
              type="number"
              min={1}
              max={32000}
              value={maxTokens}
              onChange={(e) => onMaxTokensChange(Number(e.target.value))}
              className="w-full rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
            />
          </div>
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="System prompt"
        icon={Terminal}
        defaultOpen={false}
        summary={systemPrompt ? `${systemPrompt.slice(0, 24)}…` : "Not set"}
      >
        <div className="pt-3">
          <textarea
            value={systemPrompt}
            onChange={(e) => onSystemPromptChange(e.target.value)}
            placeholder="You are a helpful assistant…"
            rows={4}
            aria-label="System prompt"
            className="w-full resize-none rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
          />
        </div>
      </CollapsibleSection>
    </div>
  );
}
