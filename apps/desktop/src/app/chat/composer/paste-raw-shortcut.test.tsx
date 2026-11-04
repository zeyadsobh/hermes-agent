// @vitest-environment jsdom
import { AssistantRuntimeProvider, useExternalStoreRuntime } from '@assistant-ui/react'
import type { ThreadMessageLike } from '@assistant-ui/react'
import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { mainComposerScope } from '@/store/composer'

import { LARGE_PASTE_ATTACHMENT_THRESHOLD } from './large-paste'
import { composerPlainText, RICH_INPUT_SLOT } from './rich-editor'
import type { ChatBarState } from './types'

import { ChatBar } from './index'

afterEach(cleanup)

const LARGE_TEXT = 'word '.repeat(LARGE_PASTE_ATTACHMENT_THRESHOLD)

const state: ChatBarState = {
  model: { canSwitch: false, model: '', provider: '' },
  tools: { enabled: false, label: '' },
  voice: { enabled: false, active: false }
}

function Harness({ onAttachPastedText }: { onAttachPastedText: (text: string) => boolean }) {
  const runtime = useExternalStoreRuntime({
    convertMessage: (message: ThreadMessageLike) => message,
    isRunning: false,
    messages: [] as ThreadMessageLike[],
    onNew: async () => {}
  })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <MemoryRouter>
        <I18nProvider configClient={null} initialLocale="en">
          <ChatBar
            busy={false}
            disabled={false}
            gateway={null}
            onAttachPastedText={onAttachPastedText}
            onCancel={vi.fn()}
            onSubmit={vi.fn(async () => true)}
            state={state}
          />
        </I18nProvider>
      </MemoryRouter>
    </AssistantRuntimeProvider>
  )
}

function setup(onAttachPastedText: (text: string) => boolean) {
  const { container } = render(<Harness onAttachPastedText={onAttachPastedText} />)
  const editor = container.querySelector<HTMLElement>(`[data-slot="${RICH_INPUT_SLOT}"]`)!

  Object.defineProperty(editor, 'isContentEditable', { configurable: true, value: true })
  editor.focus()

  return editor
}

function paste(editor: HTMLElement, text: string) {
  const event = new Event('paste', { bubbles: true, cancelable: true }) as ClipboardEvent

  Object.defineProperty(event, 'clipboardData', {
    value: { getData: (type: string) => (type === 'text' || type === 'text/plain' ? text : ''), files: [], items: [] }
  })

  act(() => {
    fireEvent(editor, event)
  })
}

describe('Ctrl+Shift+V raw paste', () => {
  afterEach(() => {
    mainComposerScope.clear()
  })

  it('attaches a large plain paste as a file', async () => {
    const onAttachPastedText = vi.fn(() => true)
    const editor = setup(onAttachPastedText)

    paste(editor, LARGE_TEXT)

    expect(onAttachPastedText).toHaveBeenCalledTimes(1)
    expect(composerPlainText(editor)).toBe('')
  })

  it('inserts a large paste into the input when Ctrl+Shift+V armed it, once', () => {
    const onAttachPastedText = vi.fn(() => true)
    const editor = setup(onAttachPastedText)

    fireEvent.keyDown(editor, { key: 'V', ctrlKey: true, shiftKey: true })
    paste(editor, LARGE_TEXT)

    expect(onAttachPastedText).not.toHaveBeenCalled()
    expect(composerPlainText(editor).length).toBeGreaterThan(LARGE_PASTE_ATTACHMENT_THRESHOLD)

    paste(editor, LARGE_TEXT)

    expect(onAttachPastedText).toHaveBeenCalledTimes(1)
  })
})
