import { Tabs as BaseTabs } from "@base-ui/react/tabs";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Tabs = BaseTabs.Root;

export function TabsList({ className, ...props }: ComponentProps<typeof BaseTabs.List>) {
  return (
    <BaseTabs.List
      className={cn("grid grid-flow-col gap-1 rounded-lg bg-stone-200 p-1", className)}
      {...props}
    />
  );
}

export function TabsTab({ className, ...props }: ComponentProps<typeof BaseTabs.Tab>) {
  return (
    <BaseTabs.Tab
      className={cn(
        "rounded-md px-3 py-1.5 text-sm font-medium text-stone-600 data-[active]:bg-white data-[active]:text-stone-900 data-[active]:shadow-sm",
        className,
      )}
      {...props}
    />
  );
}
