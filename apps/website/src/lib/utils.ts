// cn() lives in @costorah/shared-ui — this file re-exports it so the
// ~40 existing "@/lib/utils" import sites in this app don't all need
// touching. See packages/shared-ui/src/cn.ts for the implementation.
export { cn } from "@costorah/shared-ui";
