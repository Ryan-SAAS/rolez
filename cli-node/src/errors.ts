export const EXIT_OK = 0;
export const EXIT_USAGE = 1;
export const EXIT_AUTH = 2;
export const EXIT_NOT_FOUND = 3;
export const EXIT_NETWORK = 4;
export const EXIT_CALLER = 5;

export class CliError extends Error {
  constructor(
    public code: number,
    message: string,
  ) {
    super(message);
  }
}

export function die(code: number, message: string): never {
  process.stderr.write(`rolez: ${message}\n`);
  process.exit(code);
}
