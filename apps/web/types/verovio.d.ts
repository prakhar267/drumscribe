declare module "verovio/wasm" {
  export interface VerovioModule {
    cwrap: (...arguments_: unknown[]) => (...arguments_: unknown[]) => unknown;
  }

  export default function createVerovioModule(options?: Record<string, unknown>): Promise<VerovioModule>;
}

declare module "verovio/esm" {
  import type { VerovioModule } from "verovio/wasm";

  export class VerovioToolkit {
    constructor(module: VerovioModule);
    destroy(): void;
    getPageCount(): number;
    getVersion(): string;
    loadData(data: string): boolean;
    renderToSVG(pageNumber?: number, xmlDeclaration?: boolean): string;
    setOptions(options: Record<string, unknown>): void;
  }
}
