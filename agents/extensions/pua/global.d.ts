declare module "@earendil-works/pi-coding-agent" {
  export interface ExtensionAPI {
    on(event: "session_start" | "tool_result" | "before_agent_start", handler: (event: any, ctx: any) => any | Promise<any>): void;
    registerCommand(name: string, def: { description: string; handler: (args: string[], ctx: any) => any | Promise<any> }): void;
  }
}

declare module "node:fs" {
  export function existsSync(path: string): boolean;
  export function mkdirSync(path: string, options?: { recursive?: boolean }): void;
  export function readFileSync(path: string, encoding: BufferEncoding | string): string;
  export function writeFileSync(path: string, data: string, encoding: BufferEncoding | string): void;
}

declare module "node:os" {
  export function homedir(): string;
}

declare module "node:path" {
  export function join(...paths: string[]): string;
}

type BufferEncoding = "utf8" | "utf-8" | string;
