declare module 'd3-force' {
  export function forceRadial(radius: number | ((node: any) => number), x?: number, y?: number): any;
  export function forceCollide(radius: number | ((node: any) => number), x?: number, y?: number): any;
  export function forceX(x: number | ((node: any) => number), x?: number, y?: number): any;
  export function forceY(y: number | ((node: any) => number), x?: number, y?: number): any; 
}


