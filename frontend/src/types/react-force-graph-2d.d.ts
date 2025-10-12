declare module 'react-force-graph-2d' {
  import * as React from 'react';

  export type NodeObject = any;
  export type LinkObject = any;

  export interface ForceGraphMethods {
    d3Force(name: string, force?: any): any;
  }

  const ForceGraph2D: React.ComponentType<any>;
  export default ForceGraph2D;
}


