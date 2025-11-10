/// <reference types="@react-three/fiber" />

// give TS a hole it can drop these JSX tags into
declare global {
  namespace JSX {
    interface IntrinsicElements {
      ambientLight: any;
      directionalLight: any;
      mesh: any;
      meshStandardMaterial: any;
    }
  }
}

export {};
