import gradio as gr




CUSTOM_CSS = """
body { background: #0A0A0F; color: #F0F4FF; font-family: 'Courier New', monospace; }
.node-info { padding: 12px; background: rgba(0,229,255,0.06); border-left: 3px solid #00E5FF; margin-bottom: 12px; border-radius: 4px; }
.node-id { font-family: monospace; color: #00FF88; font-weight: bold; }
.status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; margin-left: 8px; }
.status-on { background: #00FF8833; color: #00FF88; border: 1px solid #00FF88; }
.status-off { background: #FF000033; color: #FF5555; border: 1px solid #FF5555; }
"""


def _history_to_messages(history):
    result = []
    for entry in history[-50:]:
        role = entry.get("role", "?")
        content = entry.get("content", "")
        if role == "user":
            result.append({"role": "user", "content": content})
        else:
            result.append({"role": "assistant", "content": content})
    return result


def _contacts_to_choices(contacts):
    choices = []
    for c in contacts:
        pid = c.get("peer_id", "")
        alias = c.get("alias", "").strip()
        count = int(c.get("message_count", 0))
        last = (c.get("last_message", "") or "").strip()
        last_preview = (last[:30] + "...") if len(last) > 30 else last
        if alias:
            label = f"{alias}  ({pid[:8]})  [{count} msgs]"
        else:
            label = f"{pid[:8]}...{pid[-4:]}  [{count} msgs]"
        if last_preview:
            label += f"  - last: {last_preview}"
        choices.append((label, pid))
    return choices


def _status_badges(brain):
    mqtt_ok = brain.mqtt.enabled if hasattr(brain, "mqtt") and brain.mqtt else False
    chat_ok = brain.chat.enabled if hasattr(brain, "chat") and brain.chat else False
    mqtt_cls = "status-on" if mqtt_ok else "status-off"
    chat_cls = "status-on" if chat_ok else "status-off"
    return (
        f"<span class='status-badge {mqtt_cls}'>MQTT {'ON' if mqtt_ok else 'OFF'}</span>"
        f"<span class='status-badge {chat_cls}'>CHAT {'ON' if chat_ok else 'OFF'}</span>"
    )


def build_ui(ohm_instance, peer_name: str, own_port: int):
    node_id = ohm_instance.node_id
    chat = ohm_instance.chat

    def _contacts_update(keep_value=None):
        choices = _contacts_to_choices(chat.list_contacts())
        if keep_value:
            return gr.update(choices=choices, value=keep_value)
        return gr.update(choices=choices)

    def refresh_history(peer_id):
        peer_id = (peer_id or "").strip()
        if not peer_id:
            return []
        return _history_to_messages(chat.get_history(peer_id))

    def do_refresh_contacts(current_peer=None):
        return _contacts_update(keep_value=(current_peer or None))

    def do_select_contact(selected):
        return selected if selected else ""

    def do_save_alias(peer_id, alias):
        peer_id = (peer_id or "").strip()
        if not peer_id:
            return "peer_id required", _contacts_update()
        chat.set_alias(peer_id, alias or "")
        return f"alias saved for {peer_id[:8]}", _contacts_update(keep_value=peer_id)

    def do_remove_contact(peer_id):
        peer_id = (peer_id or "").strip()
        if not peer_id:
            return "peer_id required", _contacts_update()
        ok = chat.remove_contact(peer_id)
        return (f"removed: {peer_id[:8]}" if ok else f"not found: {peer_id[:8]}"), _contacts_update()

    def do_handshake(peer_id):
        peer_id = (peer_id or "").strip()
        if not peer_id:
            return "peer_id required", gr.update(), _contacts_update()
        if not chat.enabled:
            return "chat disabled (cryptography not installed)", gr.update(), _contacts_update()
        if not chat.mqtt or not chat.mqtt.enabled:
            return "broker offline - run run_local_broker.py", gr.update(), _contacts_update()
        ok = chat.send_handshake(peer_id)
        msg = f"handshake {'sent' if ok else 'failed'} to {peer_id[:8]} - wait 2s"
        return msg, refresh_history(peer_id), _contacts_update(keep_value=peer_id)

    def do_send(peer_id, message, history_state):
        peer_id = (peer_id or "").strip()
        message = (message or "").strip()
        if not peer_id:
            return "peer_id required", gr.update(), history_state, _contacts_update()
        if not message:
            return "empty message", gr.update(), history_state, _contacts_update()
        if not chat.enabled:
            return "chat disabled", message, history_state, _contacts_update()
        if not chat.mqtt or not chat.mqtt.enabled:
            return "broker offline", message, history_state, _contacts_update()
        try:
            result = chat.send(peer_id, message)
        except Exception as e:
            return f"error: {e}", message, history_state, _contacts_update()
        status = result.get("status")
        if status == "SENT":
            new_hist = refresh_history(peer_id)
            return f"sent to {peer_id[:8]}", gr.update(value=""), new_hist, _contacts_update(keep_value=peer_id)
        if status == "HANDSHAKE_SENT":
            return "handshake started - wait 2s and resend", message, history_state, _contacts_update(keep_value=peer_id)
        return f"status: {status}", message, history_state, _contacts_update()

    def do_refresh_history(peer_id):
        return refresh_history(peer_id)

    def do_status():
        s = chat.status()
        return (
            f"node: {s['node_id']}\n"
            f"enabled: {s['enabled']}\n"
            f"sessions: {s['active_sessions']}\n"
            f"contacts: {s['contacts']}\n"
            f"peers: {', '.join(p[:8] for p in s['peers']) or 'none'}\n"
            f"msgs: {s['total_messages']}"
        )

    def do_tick(peer_id):
        return _contacts_update(keep_value=(peer_id or None)), refresh_history(peer_id)

    def do_pipeline(query):
        try:
            resp = ohm_instance.think(query or "", origin="local")
            from ohm_synapse import CitationFormatter
            return CitationFormatter.format(resp)
        except Exception as e:
            return f"error: {e}"


    with gr.Blocks(title=f"OHM {peer_name}") as demo:
        gr.HTML(
            f'<div class="node-info">'
            f'<b>{peer_name}</b> | port {own_port} | '
            f'node_id: <span class="node-id">{node_id}</span>'
            f'{_status_badges(ohm_instance)}'
            f'</div>'
        )

        with gr.Tab("Chat E2EE"):
            gr.Markdown(
                "**Flow:** pick a contact from the list (or paste a new node_id) "
                "-> **Handshake** -> wait 2s -> send messages."
            )

            with gr.Row():
                contacts_dd = gr.Dropdown(
                    label="Contacts",
                    choices=_contacts_to_choices(chat.list_contacts()),
                    interactive=True,
                    allow_custom_value=False,
                    scale=5,
                )
                refresh_contacts_btn = gr.Button("Refresh contacts", scale=1)

            with gr.Row():
                peer_input = gr.Textbox(
                    label="Peer node_id (target)",
                    placeholder="select a contact above or paste a new id",
                    scale=4,
                )
                hs_btn = gr.Button("Handshake", variant="secondary", scale=1)

            with gr.Row():
                alias_input = gr.Textbox(
                    label="Contact alias (optional)",
                    placeholder="e.g. John - iPhone",
                    scale=4,
                )
                save_alias_btn = gr.Button("Save alias", scale=1)
                remove_contact_btn = gr.Button("Remove contact", variant="stop", scale=1)

            chat_bot = gr.Chatbot(
                label="History",
                height=340,
                show_label=True,
            )

            msg_input = gr.Textbox(
                label="Message",
                placeholder="text encrypted with AES-GCM",
                lines=2,
            )

            with gr.Row():
                send_btn = gr.Button("Send encrypted", variant="primary", scale=2)
                refresh_btn = gr.Button("Refresh history", scale=1)
                status_btn = gr.Button("Status", scale=1)

            log_box = gr.Textbox(label="Log", lines=2, interactive=False)

            contacts_dd.change(do_select_contact, [contacts_dd], [peer_input])
            refresh_contacts_btn.click(do_refresh_contacts, [peer_input], [contacts_dd])
            hs_btn.click(do_handshake, [peer_input], [log_box, chat_bot, contacts_dd])
            save_alias_btn.click(do_save_alias, [peer_input, alias_input], [log_box, contacts_dd])
            remove_contact_btn.click(do_remove_contact, [peer_input], [log_box, contacts_dd])
            send_btn.click(do_send, [peer_input, msg_input, chat_bot], [log_box, msg_input, chat_bot, contacts_dd])
            msg_input.submit(do_send, [peer_input, msg_input, chat_bot], [log_box, msg_input, chat_bot, contacts_dd])
            refresh_btn.click(do_refresh_history, [peer_input], [chat_bot])
            status_btn.click(do_status, [], [log_box])

            try:
                auto_timer = gr.Timer(value=3.0, active=True)
                auto_timer.tick(do_tick, [peer_input], [contacts_dd, chat_bot])
            except Exception:
                demo.load(do_tick, [peer_input], [contacts_dd, chat_bot], every=3.0)

        with gr.Tab("Pipeline"):
            gr.Markdown("Commands: `/remember`, `/audit`, `/forget`, `/correct`, `/fib`, `/help`")
            query_input = gr.Textbox(label="Query", lines=2)
            send_query = gr.Button("Run", variant="primary")
            result_box = gr.Textbox(label="Response", lines=15, interactive=False)
            send_query.click(do_pipeline, [query_input], [result_box])
            query_input.submit(do_pipeline, [query_input], [result_box])

        with gr.Tab("Help"):
            gr.Markdown(
                f"""
### {peer_name} at http://localhost:{own_port}

**Chat E2EE flow:**
1. Pick a contact in the **Contacts** dropdown (or paste a new `node_id`)
2. Click **Handshake** and wait 2s
3. Type a message and click **Send encrypted**
4. History auto-updates every 3s

**Contacts:**
- Fill the **Alias** field and click **Save alias** to name a peer
- Click **Remove contact** to drop it from the list
- Contacts and history persist in `./ohm_data/<peer>/`

**Auto-update:** contacts dropdown and history refresh every 3s.
                """
            )

    return demo