/**
 * Type declarations for the Vidstack CDN bundle.
 *
 * The CDN build (`https://cdn.vidstack.io/player`) uses different export
 * names than the `vidstack` npm package and has no shipped types.  This
 * stub declares the subset of the API surface we rely on.
 */
declare module "https://cdn.vidstack.io/player" {

  export interface PlayerState {
    mediaWidth(): number;
    mediaHeight(): number;
  }

  export interface PlayerControls {
    show(): void;
  }

  export interface Player {
    currentTime: number;
    playbackRate: number;
    duration: number;
    paused: boolean;
    $state: PlayerState;
    controls: PlayerControls;

    play(): Promise<void>;
    pause(): void;
    destroy(): void;

    addEventListener(
      event: string,
      handler: (...args: any[]) => void,
      opts?: AddEventListenerOptions,
    ): void;
  }

  export const VidstackPlayer: {
    create(opts: {
      target: string;
      title?: string;
      src?: string;
      layout?: VidstackPlayerLayout;
      autoplay?: boolean;
      [key: string]: any;
    }): Promise<Player>;
  };

  export class VidstackPlayerLayout {
    constructor(opts?: Record<string, any>);
  }
}
