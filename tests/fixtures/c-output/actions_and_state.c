/* Generic generated-C regression: actions, mutable state, callbacks and resources. */
typedef void (*handler_t)(int);
typedef struct { int counter; unsigned mode; int history[4]; } app_state_t;
app_state_t app_state = {1, 0, {0, 0, 0, 0}};
const unsigned short resource_samples[] = {3, 5, 7, 11};
static void action_add(int n) { app_state.counter += n; }
static void action_multiply(int n) { app_state.counter *= n; }
void dispatch_event(int event, int value) {
    handler_t callback = 0;
    switch (event) {
    case 0: callback = action_add; break;
    case 1: callback = action_multiply; break;
    default: app_state.mode = (app_state.mode + 1) % 3; break;
    }
    if (callback) callback(value);
    for (unsigned i = 3; i > 0; --i) app_state.history[i] = app_state.history[i - 1];
    app_state.history[0] = app_state.counter;
}
int state_checksum(void) {
    int value = app_state.counter * 100 + app_state.mode * 10;
    for (unsigned i = 0; i < 4; ++i) value += app_state.history[i] + resource_samples[i];
    return value;
}
