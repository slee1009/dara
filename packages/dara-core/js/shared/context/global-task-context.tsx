import * as React from 'react';
import { useRecoilCallback } from 'recoil';

import { cancelTask } from '@/api';
import { useSessionToken } from '@/auth/auth-context';
import { TriggerIndexValue, atomRegistry } from '@/shared/interactivity/store';

export interface GlobalTaskContext {
    /**
     * Cleanup tasks related to the given variables
     */
    cleanupRunningTasks: (...variableIds: string[]) => void;

    /**
     * Remove a task from registered running tasks
     */
    endTask: (taskId: string) => void;

    /**
     * Get tasks related to given variables
     */
    getVariableTasks: (...variableIds: string[]) => string[];

    /**
     * Check if there are any tasks currently running
     */
    hasRunningTasks: () => boolean;

    /**
     * Register a task being started
     */
    startTask: (taskId: string, variableId?: string, triggerKey?: string) => void;
}

const GlobalTaskCtx = React.createContext<GlobalTaskContext>(null);

/**
 * Represents a task run
 */
export interface VariableTaskEntry {
    /** Task ID */
    taskId: string;
    /** Key of the trigger to increment in order to reset the associated selector */
    triggerKey: string;
}

interface GlobalTaskProviderProps {
    children: JSX.Element;
    tasks?: Set<string>;
    variableTaskMap?: Map<string, Array<VariableTaskEntry>>;
}

export default function GlobalTaskProvider({ tasks, variableTaskMap, children }: GlobalTaskProviderProps): JSX.Element {
    /**
     * Set holding all currently running tasks
     */
    const tasksRef = React.useRef<Set<string>>(tasks ?? new Set());

    /**
     * Map of variableId -> Array(VariableTaskEntry)
     */
    const mapRef = React.useRef<Map<string, Array<VariableTaskEntry>>>(variableTaskMap ?? new Map());

    const token = useSessionToken();

    const refreshSelector = useRecoilCallback(({ set }) => (key: string) => {
        // refresh the selector by incrementing the associated trigger so next run will skip the cache
        set(atomRegistry.get(key), (prev: TriggerIndexValue) => ({ ...prev, inc: prev.inc + 1 }));
    });

    const cleanupRunningTasks = React.useCallback(
        (...variableIds: string[]): void => {
            for (const variableId of variableIds) {
                const taskEntries = mapRef.current.get(variableId);

                // check if any of the currently running tasks are associated with the variable
                for (const runningTask of tasksRef.current) {
                    const taskToCancel = taskEntries?.find((t) => t.taskId === runningTask);

                    // found a match
                    if (taskToCancel) {
                        // cancel the task and mark it as stopped
                        cancelTask(runningTask, token);
                        tasksRef.current.delete(runningTask);

                        // make sure next time the selector runs it will run from scratch rather than using the cached value
                        refreshSelector(taskToCancel.triggerKey);
                    }
                }
            }
        },
        [token]
    );

    const startTask = React.useCallback((taskId: string, variableId?: string, triggerKey?: string): void => {
        if (variableId) {
            // add the task to the variable -> tasks map
            const variableTaskEntries = mapRef.current.get(variableId) ?? [];
            variableTaskEntries.push({ taskId, triggerKey });
            mapRef.current.set(variableId, variableTaskEntries);
        }

        tasksRef.current.add(taskId);
    }, []);

    const endTask = React.useCallback((taskId: string): void => {
        tasksRef.current.delete(taskId);
    }, []);

    const getVariableTasks = React.useCallback((...variableIds: string[]): string[] => {
        let taskIds: string[] = [];

        for (const variable of variableIds) {
            const associatedTasks = mapRef.current.get(variable);

            // If there are associated tasks in the map
            if (associatedTasks) {
                // check which ones are currently running
                taskIds = associatedTasks
                    .filter((entry) => tasksRef.current.has(entry.taskId))
                    .map((entry) => entry.taskId);
            }
        }

        return taskIds;
    }, []);

    const hasRunningTasks = React.useCallback((): boolean => {
        return tasksRef.current.size > 0;
    }, []);

    return (
        <GlobalTaskCtx.Provider value={{ cleanupRunningTasks, endTask, getVariableTasks, hasRunningTasks, startTask }}>
            {children}
        </GlobalTaskCtx.Provider>
    );
}

export function useTaskContext(): GlobalTaskContext {
    const taskCtx = React.useContext(GlobalTaskCtx);

    if (taskCtx === undefined) {
        throw new Error('useTaskContext must be used within GlobalTaskProvider');
    }

    return taskCtx;
}
